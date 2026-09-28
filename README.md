# YOLO RTSP Veri Toplayıcı

RTSP kameradan GStreamer ile kare alır, seçilen Ultralytics `.pt` nesne tespit modeliyle işler ve tahmin içeren kareleri onay listesine ekler. Yalnızca onaylanan görseller ile seçilen kutular YOLO veri setine yazılır.

## Çalıştırma

Bu cihazdaki `/home/waky/.venvs/vision` Python ortamı kullanılır. Ortamın özel CUDA OpenCV derlemesi sistemde olmayan `libOpenEXR-3_4.so.33` bağına sahip olduğundan uyumlu OpenCV 4.11 yalnızca bu projenin `vendor` klasörüne kurulmuştur. Yeniden kurmak için:

```bash
/home/waky/.venvs/vision/bin/python -m pip install --target ./vendor --no-deps opencv-python-headless==4.11.0.86
```

```bash
bash run.sh
```

Arayüz: `http://127.0.0.1:8765`. **Dosya seç** düğmesi cihazın dosya seçicisini açar. Seçilen `.pt` dosyası proje içindeki `models/` klasörüne kopyalanır ve model yolu otomatik doldurulur. Dilerseniz tam dosya yolunu elle de girebilirsiniz. Modeldeki sınıflar otomatik okunur; **Sınıfları göster** ile tekrar yükleyebilirsiniz. İşlenmesini istediğiniz sınıfları işaretleyin. RTSP adresini girdikten sonra **Bağlan ve başlat** düğmesine basın. Model cihazda mevcut bir Ultralytics *detection* checkpoint'i olmalı. Örnek çalışan model: `/home/waky/Projeler/ocr_project/models/license-plate-finetune-v1l.pt`. `partCheck/outputs/10091012/best_model.pt` dosyası Ultralytics checkpoint biçiminde değil.

## Kullanım

- `ffprobe` akışın H.264/H.265 codec'ini belirler. GStreamer `rtspsrc` ve yazılım çözümü ile JPEG kareleri alır.
- Çıkarımın bulunduğu kareler belirlenen saniye aralığında otomatik olarak `pending/` klasörüne eklenir. En fazla 500 aday bekletilir. **Bu kareyi aday yap** düğmesi işlenen son kareyi ayrıca ekler.
- Adayda kutu seçimini değiştirebilir, **Onayla** veya **Reddet** diyebilirsiniz. Eksik/hatalı kutulu görselleri reddedin; arayüz şu aşamada yeni kutu çizmez.
- Onaylanan veriler `dataset/images/train`, `dataset/labels/train`, `dataset/classes.txt` ve `dataset/data.yaml` dosyalarında tutulur. Sınıflar model adına göre eşleştirilir; YOLO satırları `class_id x_center y_center width height` biçimindedir. Hiç kutu seçmeden onaylamak boş etiket dosyası oluşturur.
- Bekleyen adaylar uygulama yeniden başlatıldığında korunur.

## Cihaz durumu

GStreamer 1.28.7, `rtspsrc`, H.264/H.265 depay/parse, `avdec_h264`, `avdec_h265`, `videoconvert`, `jpegenc` ve `fdsink` kullanılır. `nvstreammux` yok. Mevcut PyTorch 2.5.1 CUDA derlemesi kurulu olsa da `torch.cuda.is_available()` false ve `nvidia-smi` sürücüyle haberleşemiyor. Uygulama bu nedenle CPU çıkarımı yapar.

Henüz gerçek RTSP adresi verilmediğinden canlı kameraya bağlantı doğrulanmadı.
