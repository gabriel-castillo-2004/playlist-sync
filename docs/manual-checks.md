# Lista de Verificación Manual y Flujo E2E (Fase 4 y Fase 7: Frontend y Sincronización "A prueba de mamá")

Esta guía describe el procedimiento paso a paso para verificar de forma visual y funcional la aplicación en un navegador de escritorio, en un dispositivo móvil (ancho de 360 px) y de extremo a extremo (PC → Syncthing → Celular).

---

## 1. Verificación de Inicio y Carga
- [x] Ejecutar el servidor con `python -m playlist_sync serve` o mediante `start.bat` / `start.sh`.
- [x] Abrir `http://localhost:8000` en el navegador (o `http://<IP-LAN>:8000` en el celular tras configurar `host = "0.0.0.0"` en `config.toml`).
- [x] **Resultado esperado:**
  - Se visualiza la cabecera con el título "Mi Música", el botón "Verificar archivos" y el botón principal "Actualizar todo".
  - Se muestra el formulario para agregar fuentes con el campo de texto "Pega un link o escribe el nombre de un podcast".
  - El botón de salud (`#system-health-pill`, navegable con teclado mediante `Tab` y `Enter`/`Espacio`) muestra "Sistema listo ✓" con punto verde.
  - El indicador de conexión muestra "En vivo" (conexión Server-Sent Events activa).
  - Si no hay fuentes, se observa el estado vacío invitando a agregar una lista.

---

## 2. Agregar Playlist Pública (Flujo Feliz)
- [x] Pegar la URL de una lista pública de prueba (ej. `https://music.youtube.com/playlist?list=PLH4CG4U26Tr0`).
- [x] Pulsar el botón **"Guardar"**.
- [x] **Resultado esperado:**
  - El botón cambia temporalmente a "Guardando...".
  - Aparece una notificación flotante de confirmación ("¡... guardada!").
  - Se genera de inmediato una tarjeta con el título de la playlist, portada, conteo inicial de canciones pendientes y el botón grande **"Descargar nuevas"**.
  - El banner superior muestra el progreso en vivo ("Descargando X de Y: [Título de canción]", barra de porcentaje progresando).
  - Al concluir la descarga, la tarjeta pasa al estado **"Al día ✓"** con fondo verde suave.

---

## 3. Detección Temprana de Playlist Privada (RF-3)
- [x] Pegar un link de una playlist privada o inaccesible (o un enlace inventado privado).
- [x] Pulsar **"Guardar"**.
- [x] **Resultado esperado:**
  - No se realiza ninguna descarga ni se crea tarjeta.
  - Se muestra un aviso en recuadro con mensaje claro en español:
    > *"Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar."*
  - El aviso cuenta con un botón de cierre (&times;) que lo oculta al tocarlo.

---

## 4. Detección de Enlace Inválido y Errores de Fuente (H-09)
- [x] Escribir un enlace con esquema inválido en el formulario (ej. `ftp://invalido`).
- [x] Pulsar **"Guardar"**.
- [x] **Resultado esperado:**
  - Se despliega un mensaje claro en español sin exponer trazas técnicas (`technical_detail`).
  - Si una fuente registrada cae en estado `error` (ej. caída por debajo del umbral del 50 % o fallo de red), su tarjeta muestra la insignia **"Hubo un problema"** y el motivo (`last_error_message`), nunca **"Al día ✓"**.

---

## 5. Inspección de Canciones y Reintentos (RF-8 / H-12)
- [x] En la tarjeta de una lista, pulsar el botón **"Ver canciones"**.
- [x] **Resultado esperado:**
  - Se despliega la lista de canciones con su estado individual (✓ para descargadas).
  - Si alguna canción presentó fallo, la fila se destaca con el motivo legible en español.
  - En las canciones con error se muestra un botón **"Reintentar"**. Al pulsarlo (cuando no hay otra descarga activa), el sistema reinicia el contador de intentos a `0` y programa la sincronización en segundo plano.

---

## 6. Candado de Concurrencia (RF-11 / H-11)
- [x] Mientras una lista se está descargando activamente, pulsar el botón de actualizar en otra tarjeta o el botón superior "Actualizar todo".
- [x] **Resultado esperado:**
  - La aplicación rechaza solicitudes concurrentes con `409 Conflict` y muestra una notificación:
    > *"Ya hay una descarga en curso. Espera a que termine."*
  - No se inician dos descargas paralelas ni se altera el estado de reintentos mientras el candado está ocupado.

---

## 7. Reconciliación con Disco y Respaldos (RF-20 / H-02)
- [x] Ejecutar `python -m playlist_sync reconcile` o pulsar el botón **"Verificar archivos"** en la interfaz web tras importar `sources.json` sobre una carpeta `music_root` con archivos `[{external_id}].mp3` ya descargados.
- [x] **Resultado esperado:**
  - Las canciones existentes en disco se marcan automáticamente como `downloaded` sin volver a descargarlas y se regenera el archivo `.m3u8`.
- [x] Ejecutar `python -m playlist_sync backup` y `python -m playlist_sync restore-backup <archivo.sqlite3>`.
- [x] **Resultado esperado:**
  - Se conservan hasta 5 respaldos íntegros (no vacíos) fuera de `music_root` y la restauración verifica `PRAGMA integrity_check` antes de recuperar la base de datos.

---

## 8. Contingencia ante Pérdida de Conexión y Modo Oscuro
- [x] Desconectar momentáneamente la conexión SSE y verificar que el indicador cambie a "Respaldo (5s)" y vuelva a "En vivo" al reconectar.
- [x] Probar la interfaz cambiando el tema del sistema operativo entre Modo Claro y Modo Oscuro (`prefers-color-scheme`).

---

## 9. Verificación E2E de Fase 7 (Linux Mint + Servicio `systemd` + Syncthing + Reproductor Móvil)
- [x] **Pruebas E2E automatizadas (`tests/e2e/test_ui_playwright.py` y `pytest -m network`):**
  - Alta de fuente → primera sincronización → generación de archivos `.mp3` con sufijo `[external_id]`, carátula `APIC`, etiquetas ID3v2.3 (`TIT2`, `TPE1`, `TALB`, `TRCK`) y `.m3u8` con rutas relativas → segunda corrida estrictamente idempotente (`0` descargas repetidas).
- [ ] **Verificación física en red doméstica con el teléfono (a completar con el dispositivo móvil emparejado):**
  - Verificar servicio activo tras reinicio sin sesión gráfica (`systemctl --user status playlist-sync.service` con `loginctl enable-linger`).
  - Emparejar `music_root` en Syncthing (PC en modo *Solo enviar*, celular con Syncthing-Fork en modo *Solo recibir*).
  - Abrir el reproductor móvil (Musicolet / AIMP / Poweramp / VLC) y confirmar que la lista `.m3u8`, el orden de pistas y las carátulas se visualizan correctamente.
