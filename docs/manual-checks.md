# Lista de Verificación Manual (Fase 4: Frontend "A prueba de mamá")

Esta guía describe el procedimiento paso a paso para verificar de forma visual y funcional la aplicación en un navegador de escritorio y en un dispositivo móvil (ancho de 360 px).

---

## 1. Verificación de Inicio y Carga
- [ ] Ejecutar el servidor con `python -m playlist_sync serve` o mediante `start.bat` / `start.sh`.
- [ ] Abrir `http://localhost:8000` en el navegador del celular o en el modo responsivo (360 px de ancho).
- [ ] **Resultado esperado:**
  - Se visualiza la cabecera con el título "Mi Música" y el botón principal "Actualizar todo".
  - Se muestra el formulario para agregar fuentes con el campo de texto "Pega un link o escribe el nombre de un podcast".
  - El indicador de salud muestra "Sistema listo ✓" con punto verde.
  - El indicador de conexión muestra "En vivo" (conexión Server-Sent Events activa).
  - Si no hay fuentes, se observa el estado vacío invitando a agregar una lista.

---

## 2. Agregar Playlist Pública (Flujo Feliz)
- [ ] Pegar la URL de una lista pública de prueba (ej. `https://music.youtube.com/playlist?list=PLH4CG4U26Tr0`).
- [ ] Pulsar el botón **"Guardar"**.
- [ ] **Resultado esperado:**
  - El botón cambia temporalmente a "Guardando...".
  - Aparece una notificación flotante de confirmación ("¡... guardada!").
  - Se genera de inmediato una tarjeta con el título de la playlist, portada y el botón grande **"Descargar nuevas"** o **"Actualizar"**.
  - El banner superior muestra el progreso en vivo ("Descargando: [Título de canción]", barra de porcentaje progresando).
  - Al concluir la descarga, la tarjeta pasa al estado **"Al día ✓"** con fondo verde suave.

---

## 3. Detección Temprana de Playlist Privada (RF-3)
- [ ] Pegar un link de una playlist privada o inaccesible (o un enlace inventado privado).
- [ ] Pulsar **"Guardar"**.
- [ ] **Resultado esperado:**
  - No se realiza ninguna descarga ni se crea tarjeta.
  - Se muestra un aviso en recuadro con mensaje claro en español:
    > *"Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar."*
  - El aviso cuenta con un botón de cierre (&times;) que lo oculta al tocarlo.

---

## 4. Detección de Enlace Inválido
- [ ] Escribir un texto arbitrario en el formulario (ej. `mi-musica-favorita` o `ftp://invalido`).
- [ ] Pulsar **"Guardar"**.
- [ ] **Resultado esperado:**
  - Se despliega el mensaje de error:
    > *"Ese link no parece de YouTube ni de un podcast."*

---

## 5. Inspección de Canciones y Reintentos (RF-8)
- [ ] En la tarjeta de una lista, pulsar el botón **"Ver canciones"**.
- [ ] **Resultado esperado:**
  - Se despliega la lista de canciones con su estado individual (✓ para descargadas).
  - Si alguna canción presentó fallo (por ejemplo, video borrado o error de red), la fila se destaca con el motivo legible (ej. *"Este video ya no está disponible"*).
  - En las canciones con error se muestra un botón **"Reintentar"**. Al pulsarlo, el sistema programa el reintento en segundo plano.

---

## 6. Candado de Concurrencia (RF-11)
- [ ] Mientras una lista se está descargando activamente, pulsar el botón de actualizar en otra tarjeta o el botón superior "Actualizar todo".
- [ ] **Resultado esperado:**
  - La aplicación muestra una notificación:
    > *"Ya hay una descarga en curso. Espera a que termine."*
  - No se inician dos descargas paralelas, evitando saturación de red o colisiones de archivos.

---

## 7. Contingencia ante Pérdida de Conexión (Fallback Polling)
- [ ] Desconectar momentáneamente la conexión de red o detener la conexión SSE (por ejemplo, reiniciando el servicio).
- [ ] **Resultado esperado:**
  - El indicador de conexión cambia automáticamente a "Respaldo (5s)" con punto ámbar.
  - La interfaz continúa consultando el estado cada 5 segundos sin romperse.
  - Al restaurarse la conexión, el indicador regresa a "En vivo" y el polling periódico se detiene.

---

## 8. Adaptabilidad y Modo Oscuro
- [ ] Probar la interfaz cambiando el tema del sistema operativo o navegador entre Modo Claro y Modo Oscuro.
- [ ] **Resultado esperado:**
  - Los colores, fondos, tarjetas y textos adaptan su contraste automáticamente según la preferencia del sistema (`prefers-color-scheme`).
  - La interfaz se mantiene legible, con tipografía grande y botones táctiles cómodos para operar con una sola mano.
