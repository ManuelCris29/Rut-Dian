---
name: validacion-identificacion
description: Validación y normalización de números de identificación colombianos (cédula de ciudadanía y NIT con dígito de verificación DIAN) para este proyecto, incluyendo casos de prueba. Usar al implementar o probar domain/validators.py o la lectura de archivos de entrada.
---

# Validación de identificaciones

## Normalización
1. `str(value).strip()`; si viene de Excel como número flotante (`1234567890.0`) convertir sin perder dígitos.
2. Eliminar `.`, `,`, espacios y guiones **solo** para separar DV: `900.123.456-7` → base `900123456`, dv `7`.
3. Resultado debe ser solo dígitos; si no → `ENTRADA_INVALIDA` (motivo: "contiene caracteres no numéricos").

## Reglas de longitud [SUPUESTO — confirmar con negocio]
- Cédula: 3 a 10 dígitos.
- NIT (sin DV): 9 a 10 dígitos (se acepta con o sin DV).
Rechazar vacío y valores con ceros iniciales que el negocio no acepte (pendiente de confirmar).

## Dígito de verificación (DV) del NIT
Preferir la librería **python-stdnum**, módulo `stdnum.co.nit` (funciones `calc_check_digit`, `is_valid`, `validate`, `compact`, `format`).
**Verificar la API vigente con Context7 o PyPI antes de usarla.**

Algoritmo de referencia (módulo 11 de la DIAN) para pruebas independientes:
- Pesos aplicados de **derecha a izquierda** sobre los dígitos del número base: 3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71.
- `r = suma(dígito × peso) % 11`; si `r` es 0 o 1 → DV = `r`; si no → DV = `11 − r`.

Las pruebas deben calcular el DV esperado con el algoritmo de referencia y compararlo contra la implementación (prueba de propiedad con varios números ficticios), no con DVs copiados de internet.

## Casos de prueba mínimos
| Entrada | Esperado |
|---|---|
| `""` | ENTRADA_INVALIDA (vacío) |
| `"12A45"` | ENTRADA_INVALIDA (no numérico) |
| `" 1000000001 "` | válido, normalizado `1000000001` |
| `1000000001.0` (float de Excel) | válido `1000000001` |
| NIT ficticio con DV correcto | válido |
| NIT ficticio con DV incorrecto | ENTRADA_INVALIDA (DV) |
| `"12345678901"` (11 dígitos) | ENTRADA_INVALIDA (longitud) |
