# Fixtures de prueba

Solo datos **ficticios**. El hook `proteger_datos.py` bloquea literales de 6–10 dígitos que no estén en esta lista.

## Lista blanca de identificaciones ficticias
- `1000000001` … `1000000999` (cédulas ficticias)
- `90000000x` / `90000000xx` (NIT ficticios; el DV se calcula en la prueba)
- `1234567890`, `123456789`, `12345678` (ejemplos de enmascarado)

## HTML (`html/`)
Se crean a partir del snapshot **sanitizado** documentado en `docs/investigacion/05-analisis-tecnico.md`:
`resultado_ok.html`, `sin_resultado.html`, `mantenimiento.html`, `desafio.html`, `estructura_cambiada.html`, `incompleto.html`.
Nombres de personas: "PERSONA FICTICIA UNO", "EMPRESA FICTICIA SAS".
