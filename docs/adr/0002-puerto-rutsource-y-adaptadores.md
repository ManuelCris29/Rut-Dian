# ADR-0002 — Puerto `RutSourcePort` y adaptadores de fuente

- **Estado:** ACEPTADO (2026-10-09) — D-1 y D-3 resueltas por el usuario; observaciones de
  `revisor-seguridad` (APROBADO CON OBSERVACIONES, 0 bloqueantes) incorporadas. Sujeto a ratificación en
  el gate de Fase 3.
- **Fecha:** 2026-10-09
- **Decisores:** arquitecto (propuesta), usuario (D-1, D-3), revisor-seguridad (observaciones 1, 3, 4, 7, 8, 13, 14)
- **Relacionados:** ADR-0001, ADR-0003, INFORME-VIABILIDAD §5, §8, §9; SPEC §3, §5; RN-07, RN-08

## Contexto

- La fuente de datos es incierta (SPEC §3) y la estrategia aprobada es **"C + F ahora, E condicionado"**
  (INFORME §8, decisión del usuario del 2026-10-09).
- **C — copia del RUT del tercero:** la herramienta **nunca** abre ni lee el PDF. Solo registra
  metadatos: fuente `COPIA_RUT_TERCERO`, fecha del documento, responsable que validó y observación.
  Copia con antigüedad > 30 días → `PENDIENTE_VALIDACION_MANUAL` "copia vencida" (RN-07).
- **F — contingencia manual:** genera la fila `PENDIENTE_VALIDACION_MANUAL` con fuente y fecha (RF-12).
- **E — RPA asistido sobre C-1:** se implementa, pero queda **deshabilitado por defecto** hasta cumplir
  (a)–(d). Hoy no existen selectores reales (T-14 BLOQUEADA). No se inventan selectores ni estados.
- La traducción excepción → `QueryStatus` vive en **un único lugar**: `BatchQueryService` (CLAUDE.md §6).
- Requisitos que motivan el puerto: RF-04, RF-10, RF-12, RNF-03, RNF-07, RN-07, RN-08.

## Alternativas

| # | Alternativa | Ventajas | Desventajas | Veredicto |
|---|---|---|---|---|
| 1 | Sin puerto: el servicio llama directamente a Playwright o al registro manual | Menos archivos | Acopla todo a un portal caído; imposible probar sin navegador; contradice SPEC §3 | Descartada |
| 2 | Puerto con varios métodos (`open`, `fill`, `submit`, `read`) | Control fino desde el servicio | Filtra conceptos del navegador a `application`; C y F no tienen "formulario" | Descartada |
| 3 | **Puerto mínimo `query(ident) -> RutResult` + `close()`, adaptadores intercambiables, fuente de respaldo (C + F) inyectada** | Una sola abstracción para C, F, E y pruebas; `application` no conoce Playwright | El modo asistido necesita un canal hacia el operador (segundo puerto, ADR-0003) | **Elegida** |
| 4 | Plugins descubiertos por *entry points* | Extensible | Complejidad sin requisito que la pida | Descartada |
| 5 | Leer/extraer datos del PDF de la copia del RUT | Menos digitación | **Prohibido** por la minimización de INFORME §8 y R-10 | Descartada |

## Decisión

### 1. Puerto (`src/rut_checker/ports/rut_source.py`)

```python
class RutSourcePort(Protocol):
    kind: SourceKind  # valor que se escribe en la columna `fuente`
    paced: bool  # True si consulta un sistema externo → aplica ritmo RNF-02

    def query(self, ident: IdentificationInput) -> RutResult:
        """Devuelve un resultado de negocio o lanza una RutCheckerError. Nunca devuelve datos vacíos
        silenciosos (RNF-07). No traduce excepciones a QueryStatus."""

    def close(self) -> None:
        """Libera recursos (navegador). Idempotente."""
```

- `IdentificationInput` (dominio, inmutable): `identification` (normalizado, solo dígitos, sin DV), `dv: str | None`,
  `copy_evidence: CopyEvidence | None`, `note: str | None`. No lleva `row_index` (vive en `InputRow`). Entrada = solo el número; DV opcional (P-4, [CONFIRMADO]).
- `CopyEvidence` (dominio): `document_date: date`, `responsible: str`, `note: str | None`.
  - `responsible` es un **código o usuario** (patrón `^[A-Za-z0-9._-]{2,40}$`, p. ej. `USR-001`), **no** un
    nombre completo (observación 8).
  - `note` es texto libre de longitud máxima 200; se neutraliza al exportar (ARQUITECTURA §5.3) y
    **nunca** se escribe en el log (prueba en T-43).
- `RutResult` (dominio): `status ∈ {EXITOSA, SIN_RESULTADOS, PENDIENTE_VALIDACION_MANUAL,
  VALIDADA_COPIA_RUT}`, `source: SourceKind`, `estado_rut: str | None`, `name: str | None`,
  `dv: str | None`, `observation: str | None`. Validadores de modelo:
  - `EXITOSA` exige `estado_rut` no vacío (si no → `IncompleteResult`);
  - `VALIDADA_COPIA_RUT` exige `source == COPIA_RUT_TERCERO` y `estado_rut is None and name is None` (D-3).
  Los estados de error **no** caben en `RutResult`: se expresan con excepciones y solo el servicio los convierte.
- `SourceKind` (StrEnum, dominio): `PORTAL_DIAN_C1`, `COPIA_RUT_TERCERO`, `CONTINGENCIA_MANUAL`,
  `SIN_CONSULTA`, `FAKE`.
- Excepciones de dominio con **mensaje genérico**: el adaptador captura las excepciones de terceros
  (Playwright, red, YAML) y lanza la excepción de dominio equivalente sin encadenar el texto original en
  el mensaje; nunca se registra `str(exc)`/`repr(exc)` ni el traceback de una excepción de terceros, solo
  `error_code` y nombre de clase (observación 3).

### 2. Adaptadores

| Adaptador | Archivo | `kind` | `paced` | Comportamiento | Requisito |
|---|---|---|---|---|---|
| `ContingencySource` | `adapters/contingency_source.py` | `CONTINGENCIA_MANUAL` | No | Siempre `PENDIENTE_VALIDACION_MANUAL`, observación "Pendiente de validación manual" (+ motivo que pase el servicio) | RF-12, F |
| `DocumentCopySource` | `adapters/document_copy_source.py` | `COPIA_RUT_TERCERO` | No | Si `copy_evidence` es `None` → delega en `ContingencySource`. Si existe → regla de dominio `evaluate_copy_evidence(evidence, today)`: ≤ 30 días → **`VALIDADA_COPIA_RUT`** con observación "Validado contra copia del RUT de fecha AAAA-MM-DD; responsable: <código>"; > 30 días → `PENDIENTE_VALIDACION_MANUAL` "copia vencida (AAAA-MM-DD)"; fecha futura → `PENDIENTE_VALIDACION_MANUAL` "fecha de copia inválida". `estado_rut` y `nombre_o_razon_social` quedan **vacíos** (D-3) | RN-07, C |
| `DianPortalSource` | `adapters/dian_portal/` | `PORTAL_DIAN_C1` | **Sí** | Playwright, API síncrona, navegador visible, un `BrowserContext` por lote. Orden de detección y modo asistido en ADR-0003. **Falla de forma segura** (§3). Acepta `base_url` para apuntar a un servidor local en pruebas | RF-04, RF-05, RF-10, RNF-07, E |
| `FakeSource` | `adapters/fake_source.py` | `FAKE` | No | Respuestas programables por número (resultado o excepción) y contador de llamadas, para pruebas y demos | RNF-05 |
| `ConsoleOperator` | `adapters/console_operator.py` | — | — | Implementa `OperatorPort` (ADR-0003) con `typer.echo`/`typer.confirm` | RF-10 |

La regla de 30 días es **lógica de dominio** (`domain/evidence.py`, constante `MAX_COPY_AGE_DAYS = 30`,
fecha de referencia = fecha de la ejecución en `America/Bogota`, 30 días inclusive). Cambiarla es una
decisión de negocio: requiere cambio de código revisado, no de configuración.

### 3. Selección de fuente y habilitación del portal (triple llave)

| Variable | Valores | Por defecto |
|---|---|---|
| `RUT_SOURCE` | `contingency` · `dian_portal` · `fake` | `contingency` |
| `RUT_PORTAL_ENABLED` | `true` / `false` | `false` |
| `RUT_PORTAL_APPROVAL_REF` | `APR-AAAAMMDD-n` (regex `^APR-\d{8}-\d{1,3}$`): identificador de la entrada de `docs/ESTADO.md` que registra (a)–(d) | vacío |
| `RUT_PORTAL_URL` | URL `https` con host `muisca.dian.gov.co` o que termine en `.dian.gov.co` | URL de C-1 |
| `RUT_ALLOW_FAKE` | `true` / `false` | `false` |

`build_service(settings)` en `cli.py` (DI manual, único lugar de cableado):

- `contingency` → primaria `DocumentCopySource(fallback=ContingencySource())` — **modo base C + F**.
- `fake` → `FakeSource` **solo** si `RUT_ALLOW_FAKE=true`; si no, código 2 (observación 14). La columna
  `fuente` dice `FAKE` y la CLI imprime un aviso visible "DATOS DE PRUEBA" en cada ejecución.
- `dian_portal` → primaria `DianPortalSource`, **respaldo** `DocumentCopySource(fallback=ContingencySource())`.
  Antes de abrir el navegador se verifica, en este orden; si algo falla la CLI termina con código 2 y
  mensaje explícito, **sin** degradar en silencio a otra fuente y **sin** ninguna petición de red:
  1. **Llave 1 — configuración:** `RUT_PORTAL_ENABLED=true` y `RUT_PORTAL_APPROVAL_REF` con formato
     válido → si no, `SourceNotEnabledError` ("La fuente dian_portal está deshabilitada: no se han
     registrado las condiciones (a)–(d) de INFORME-VIABILIDAD §8").
  2. **Llave 2 — settings coherentes:** `RUT_HEADLESS=false`; `RUT_PORTAL_URL` `https` y host
     `*.dian.gov.co` → validadores de `Settings`.
  3. **Llave 3 — selectores validados** (`config/selectors.yaml`, `yaml.safe_load` + Pydantic):
     - `validated: true`;
     - `synthetic` ausente o `false` (un archivo con `synthetic: true` se **rechaza** siempre en producción);
     - `approval_ref` **igual** a `RUT_PORTAL_APPROVAL_REF`;
     - `source_snapshot` apunta a un archivo existente en `docs/investigacion/`;
     - ningún selector obligatorio contiene el marcador `PENDIENTE`;
     - `detection.maintenance_url_markers` no vacío; `detection.challenge_markers` no vacío **o**
       `challenge_observed: none` con `challenge_evidence` citando el snapshot; igual para
       `detection.block_markers` / `block_observed: none`.
     → si no, `SelectorsNotValidatedError`.
  Hoy la llave 3 **siempre falla** (selectores placeholder): el adaptador no puede usarse aunque alguien
  active el flag por error. Es el comportamiento deseado.
- Si en tiempo de ejecución falta un selector obligatorio en el DOM → `StructureChanged` →
  `ESTRUCTURA_CAMBIADA` y el lote se detiene (RNF-07).

**Límite de lo que la herramienta puede verificar.** Las llaves comprueban coherencia técnica, no el
cumplimiento real. En particular, la herramienta **no puede verificar la condición (d)** (autorización
de los titulares, política de tratamiento, RNBD) ni la veracidad de (a)–(c). Por eso la entrada de
`docs/ESTADO.md` identificada por `APR-AAAAMMDD-n` debe citar la **evidencia** de cada condición (a)–(d)
con fecha y **firmante** (responsable del área jurídica / protección de datos), y solo el humano la crea.
Si la DIAN responde en contra: `RUT_PORTAL_ENABLED=false` y depuración de resultados previa
valoración jurídica (INFORME §9).

**Control de cambios propuesto (observación 1):** archivo `.github/CODEOWNERS` que exija revisión del
responsable humano para `config/selectors.yaml` y `.env.example` (se crea en T-31; los propietarios los
designa el humano).

### 4. Fuente de respaldo y "circuito abierto"

- El servicio recibe `primary: RutSourcePort` y `fallback: RutSourcePort | None`.
- Si la primaria agota reintentos con `PortalUnavailable`, la fila se resuelve con `fallback` y la
  observación incluye "Portal no disponible". El portal se considera **caído para el resto de la
  ejecución** (RNF-02, "no insistir") y las filas siguientes van directo al respaldo (Gherkin G5).
- **3 `TIEMPO_AGOTADO` seguidos** (cada uno tras sus reintentos; el contador se reinicia con `EXITOSA` o `SIN_RESULTADOS`) también abren el circuito. Constante
  no configurable (observación 13).
- Si el lote se detiene (`ESTRUCTURA_CAMBIADA`, 2 bloqueos seguidos u operador decide detener), las
  filas **no procesadas** se resuelven con el respaldo, con observación "Lote detenido: <motivo>". Así
  cada fila de entrada termina con exactamente un `QueryStatus`.

### 5. Decisiones resueltas (usuario, 2026-10-09)

- **D-1:** nuevo `QueryStatus.VALIDADA_COPIA_RUT` (añadido a `specs/excepciones.md`).
- **D-3:** el operador **no** transcribe nombre/razón social ni estado desde la copia; esas columnas
  quedan vacías en filas de copia.
- **P-4:** entrada = solo número, DV opcional, sin columna de tipo.

## Consecuencias

- (+) `application` y `domain` no conocen Playwright; C, F, E y pruebas comparten un mismo contrato.
- (+) Activar E exige configuración + selectores reales con la misma referencia de aprobación; desactivarlo, un flag.
- (+) Fallar de forma segura es el comportamiento por defecto (flag apagado, selectores sin validar, `fake` bloqueado).
- (+) El respaldo garantiza que cada fila tenga resultado y trazabilidad aunque el portal caiga.
- (−) La triple llave añade fricción deliberada a la habilitación.
- (−) La herramienta no puede comprobar (d): depende del registro firmado en `docs/ESTADO.md`.
- (−) `DocumentCopySource` depende de que el área de vinculación llene bien las columnas de copia;
  fecha ilegible o responsable inválido → `ENTRADA_INVALIDA` con motivo (no se adivina).
- Descartado `ERROR_ALMACENAMIENTO`: no hay base de datos (ningún requisito la exige).

## Estado

ACEPTADO (2026-10-09), ratificado por el usuario en el gate de Fase 3 (2026-10-09).
