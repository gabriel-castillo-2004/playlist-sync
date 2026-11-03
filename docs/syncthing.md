# Guía de Sincronización con Syncthing (PC ↔ Celular)

Esta guía explica paso a paso cómo sincronizar la música y podcasts descargados por **Playlist Sync** en tu computadora local hacia tu teléfono Android o laptop, sin depender de la nube ni de servicios de pago.

---

## 1. Principio de Operación
- **PC (Servidor de Música):** Configurada como **"Solo enviar"** (*Send Only*). La PC es la fuente de verdad.
- **Celular / Dispositivo Móvil:** Configurado como **"Solo recibir"** (*Receive Only*).
- **Independencia:** Playlist Sync organiza las carpetas y los archivos `.m3u8` en disco; Syncthing se encarga de transferirlos automáticamente cuando ambos dispositivos están en la misma red Wi-Fi (o mediante relay).

---

## 2. Aplicación recomendada para Android
> [!IMPORTANT]
> La aplicación oficial original de Syncthing en Google Play fue archivada.
> La versión recomendada y activamente mantenida es **Syncthing-Fork** (iniciada por Catfriend1 y mantenida actualmente por la comunidad en [`researchxxl/syncthing-android`](https://github.com/researchxxl/syncthing-android)), disponible en:
> - **GitHub Releases (oficial mantenido):** [researchxxl/syncthing-android](https://github.com/researchxxl/syncthing-android/releases)
> - **F-Droid:** [Syncthing-Fork en F-Droid](https://f-droid.org/packages/com.github.catfriend1.syncthingandroid/)
> - **Google Play Store:** *Syncthing-Fork*

---

## 3. Configuración Inicial Paso a Paso

### Paso 1: Instalar Syncthing en la PC
- **Linux Mint / Ubuntu:**
  ```bash
  sudo apt install syncthing
  systemctl --user enable --now syncthing.service
  ```
- **Windows:** Descargar el ejecutable o instalador de [syncthing.net](https://syncthing.net/) o mediante `winget install Syncthing.Syncthing`.
- Abrir la interfaz web en la PC: `http://127.0.0.1:8384`.

### Paso 2: Instalar y Configurar Syncthing-Fork en el Celular
1. Instala **Syncthing-Fork**.
2. Al abrirla por primera vez, concede permisos de almacenamiento para acceder a la carpeta de música (`/storage/emulated/0/Music` o la tarjeta SD).
3. **Excluir del ahorro de batería:** En los ajustes de Android, ve a *Aplicaciones > Syncthing-Fork > Batería* y selecciona **"Sin restricciones"** para que sincronice automáticamente en segundo plano mientras el teléfono carga o está conectado a Wi-Fi.

### Paso 3: Emparejar la PC con el Celular
1. En la app del celular, pulsa el icono de código QR de tu dispositivo (o ve a *Dispositivos > Agregar dispositivo*).
2. En la interfaz web de la PC (`http://127.0.0.1:8384`), pulsa **"Agregar dispositivo"** y escanea el código QR del celular (o pega el identificador de dispositivo).
3. Acepta la solicitud de emparejamiento en ambos dispositivos.

### Paso 4: Compartir la Carpeta de Música
1. En la PC, pulsa **"Agregar carpeta"**:
   - **Etiqueta de la carpeta:** `Musica`
   - **Ruta de la carpeta:** La ruta absoluta de `music_root` (ej. `/home/usuario/music_root` o `C:\Users\...\music_root`).
   - En la pestaña **"Compartir"**, marca el celular.
   - En la pestaña **"Avanzado"**, en **Tipo de carpeta**, selecciona **"Solo enviar"** (*Send Only*).
2. En el celular, aparecerá una notificación: *"Dispositivo PC desea compartir la carpeta Musica"*.
3. Pulsa sobre la notificación:
   - Elige la carpeta destino en tu celular (ej. tu carpeta principal `Music/PlaylistSync`).
   - En **Tipo de carpeta**, selecciona **"Solo recibir"** (*Receive Only*).
4. Pulsa **Guardar**.

---

## 4. Resultado en el Reproductor de Música
Una vez sincronizada la carpeta, abre cualquier reproductor de música en el celular (por ejemplo: **Musicolet**, **Opal**, **AIMP**, **Poweramp** o **VLC**):
1. Verás cada playlist de YouTube y cada podcast como una lista de reproducción lista para escuchar.
2. Todas las canciones tendrán sus nombres limpios, artista, álbum, año y carátula embebida de alta resolución.
3. Las playlists respetan el orden exacto gracias a los archivos `.m3u8` generados automáticamente.

---

## 5. Agregar un Dispositivo Nuevo
Para conectar un segundo celular, tablet o laptop:
1. Instala Syncthing en el nuevo dispositivo.
2. Empareja el nuevo dispositivo con la PC.
3. En la PC, ve a la carpeta `Musica`, pulsa *Editar > Compartir* y marca el nuevo dispositivo.
4. En el nuevo dispositivo, acepta la carpeta como **"Solo recibir"**.
5. Toda tu biblioteca se descargará de forma ordenada sin requerir ninguna acción adicional.

---

## 6. Solución de Problemas Frecuentes
- **Dispositivos no se encuentran en la red local:**
  - Verifica que el cortafuegos permita el tráfico local en el puerto **22000/TCP** (transferencia de datos) y **21027/UDP** (descubrimiento local).
- **El celular muestra "Revertir cambios locales":**
  - Si editaste o moviste un archivo en el celular, al estar en modo *Solo recibir*, Syncthing te advertirá de la diferencia. Puedes pulsar *Revertir cambios locales* para restablecer la versión idéntica de la PC.
- **Sincronización solo cuando hay Wi-Fi y cargador:**
  - En los ajustes de Syncthing-Fork, puedes activar la opción *"Sincronizar solo en Wi-Fi"* y *"Sincronizar solo cuando el dispositivo esté cargando"* para maximizar la autonomía de la batería.
