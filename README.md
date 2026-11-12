# cctv-mosaic

Server mosaic CCTV untuk ditampilkan di home TV (via app overlay `com.salam.tvwidget`).

- `server.py` — menjalankan ffmpeg persisten per kamera (MJPEG), frame terakhir ditulis atomis ke `frames/camN.jpg`, lalu disajikan via HTTP port **8090**:
  - `GET /` — halaman mosaic 2x2 + jadwal sholat (widget Kemenag)
  - `GET /frame/camN.jpg` — frame terakhir kamera N (dipakai overlay TV)
- Konfigurasi kamera ada di variabel `CAMS` (RTSP). CAM 3/4 (Han River/Tuya) masih placeholder.

## Jalanin (di STB, contoh systemd `cctv-mosaic.service`)
```bash
python3 server.py   # butuh ffmpeg; path ffmpeg di variabel FF
```
