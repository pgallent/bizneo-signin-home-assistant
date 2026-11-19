# Bizneo Signin para Home Assistant

Integración HACS que usa la geometría de una zona de Home Assistant para detectar
la entrada y salida del trabajo, conservar la jornada localmente y enviar a Bizneo
un único registro completo al salir.

> Requiere Home Assistant 2026.1 o posterior. No comparte archivos ni código con el
> CLI `bizneo_jornada.py`.

## Funcionamiento

- Acepta una entidad `person` o `device_tracker` y una entidad `zone`.
- Usa latitud, longitud, radio de zona y precisión GPS; nunca compara el nombre de la zona.
- Confirma los cruces tras un tiempo configurable dentro/fuera, conservando la hora
  original del cruce. Una reentrada cancela una salida pendiente.
- De lunes a jueves incluye pausa corta y larga; el viernes solo la larga. Las pausas
  no registradas se completan al salir dentro de sus ventanas configuradas.
- Envía un solo `POST` con la entrada, salida y todos los tramos.
- Guarda sesión, cruces, payload pendiente y fechas enviadas en `Store` de Home Assistant.
- No infiere entradas al arrancar ya dentro de la zona. Crea una notificación para
  que el usuario decida si debe iniciar la jornada manualmente.

La API disponible es de solo escritura. La integración no puede consultar si ya existe
una jornada en Bizneo, por lo que conserva sus propias fechas enviadas.

## Instalación

1. En HACS, añade este repositorio como repositorio personalizado de tipo **Integration**.
2. Instala **Bizneo Signin** y reinicia Home Assistant.
3. Ve a **Ajustes → Dispositivos y servicios → Añadir integración**.
4. Busca **Bizneo Signin** y completa el flujo. No existe configuración YAML.

Configura el dominio como `https://empresa.bizneohr.com`, sin ruta final. El token y el
ID de usuario se guardan en la entrada de configuración y nunca se incluyen en estados,
eventos, diagnósticos ni logs. Cada entrada representa un usuario Bizneo; se admiten varias.

## Ventanas y calendario

La entrada solo empieza dentro de su ventana. La salida usa una ventana normal de lunes
a jueves y otra específica para el viernes. Una salida fuera de ventana **no** cierra la
jornada: deja la sesión activa, crea una notificación y requiere
`bizneo_signin.finalizar_jornada_manual`.

Los sábados, domingos, festivos nacionales/autonómicos y fechas de `no_laborables` se
omiten. La comunidad autónoma se elige en un desplegable y sus festivos se suman a los
nacionales; con «Ninguna» solo se aplican los festivos nacionales.
Las fechas adicionales aceptan valores y rangos separados por comas o líneas:

```text
2026-03-19, 2026-04-06..2026-04-10
```

Las pausas pueden enviarse como huecos entre tramos o como descansos explícitos de Bizneo.
En el segundo caso son obligatorios los IDs de tipo de descanso corto y largo.

## Acciones

- `bizneo_signin.registrar_pausa`: `tipo: corta` o `larga`; usa la hora real de llamada.
- `bizneo_signin.iniciar_jornada_manual`: recupera una entrada ausente.
- `bizneo_signin.finalizar_jornada_manual`: cierra y envía la sesión activa.
- `bizneo_signin.descartar_jornada`: borra solo el estado local actual.
- `bizneo_signin.reintentar_envio`: disponible únicamente para fallos inequívocos.
- `bizneo_signin.resolver_envio_dudoso`: tras comprobar Bizneo, indica `creado` o
  `no_creado`.

Si hay varias cuentas, añade `config_entry_id` a la acción. Las acciones manuales aceptan
opcionalmente `hora` en ISO 8601; si se omite usan la hora actual.

## Automatizaciones de pausas aleatorias

La integración sortea la duración cuando esa opción está habilitada. El instante de llamada
siempre es real; para sortearlo, usa un `delay` propio de Home Assistant. Ejemplo de pausa
corta entre 10:00 y 11:00 de lunes a jueves:

```yaml
alias: Bizneo - pausa corta aleatoria
triggers:
  - trigger: time
    at: "10:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.bizneo_signin_jornada_activa
    state: "on"
  - condition: template
    value_template: "{{ now().weekday() < 4 }}"
actions:
  - delay:
      minutes: "{{ range(0, 61) | random }}"
  - action: bizneo_signin.registrar_pausa
    data:
      tipo: corta
mode: single
```

Crea otra automatización equivalente para la pausa larga dentro de su ventana. La acción
rechaza duplicados, pausas sin jornada y llamadas fuera de ventana.

## Entidades y eventos

- `binary_sensor.bizneo_signin_jornada_activa`
- `sensor.bizneo_signin_estado_de_jornada`
- `sensor.bizneo_signin_ultima_jornada`

El estado puede ser `idle`, `entry_pending`, `working`, `exit_pending`, `submitting`,
`submitted`, `failed` o `uncertain`. Se publican los eventos
`bizneo_signin_started`, `bizneo_signin_pause`, `bizneo_signin_exit`,
`bizneo_signin_submitted` y `bizneo_signin_error`.

## Errores y seguridad frente a duplicados

La integración solo reintenta automáticamente HTTP 429, HTTP 503 y fallos claros al abrir
la conexión. Un timeout, un corte durante la respuesta, un HTTP 5xx distinto o un reinicio
durante el envío quedan en `uncertain`; comprueba Bizneo antes de resolverlos. Un 401/403
inicia reautenticación y un 404 pide revisar dominio e ID de usuario.

## Desarrollo y releases

```bash
python3 -m pip install -r requirements_test.txt
python3 -m pytest
python3 -m compileall -q custom_components
```

Las validaciones de HACS y hassfest se ejecutan en GitHub Actions. Las releases deben usar
SemVer (`v0.1.0`, `v0.2.0`, `v1.0.0`) y mantener el mismo valor sin `v` en `manifest.json`.

## Desinstalación

Elimina primero la entrada desde **Ajustes → Dispositivos y servicios**, después desinstala
el repositorio desde HACS y reinicia Home Assistant. Al descargar la entrada se cancelan
listeners y temporizadores; al eliminarla también se borra su estado local privado. Los
registros ya creados en Bizneo no se modifican.

## Licencia

[MIT](LICENSE)
