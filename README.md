# YOLO RTSP Veri Toplayıcı

RTSP kameradan GStreamer ile kare alır. Kullanıcı kamera önizlemesinde çokgen ROI seçip toplamayı başlattıktan sonra, seçilen Ultralytics `.pt` nesne tespit modeliyle ROI görüntüsünü işler ve tahmin içeren kareleri onay listesine ekler. Yalnızca onaylanan görseller ile seçilen kutular YOLO veri setine yazılır.

## Çalıştırma

`run.sh` Python ortamını şu sırayla seçer: `VISION_PYTHON` ortam değişkeni, varsa `/home/waky/.venvs/vision/bin/python`, yoksa `PATH` içindeki `python3`. Ortamda `opencv`, `numpy` ve `ultralytics` kurulu olmalıdır. Proje içinde `vendor/` klasörü varsa `PYTHONPATH`'e önce o eklenir.

`/home/waky/.venvs/vision` ortamının özel CUDA OpenCV derlemesi sistemde olmayan `libOpenEXR-3_4.so.33` bağına sahip olduğundan o cihazda uyumlu OpenCV 4.11 `vendor` klasörüne kurulur:

```bash
/home/waky/.venvs/vision/bin/python -m pip install --target ./vendor --no-deps opencv-python-headless==4.11.0.86
```

Çıkarım cihazı `AUTO_LABELLER_DEVICE` ile seçilir (`cpu`, `0`, `cuda:0`…). Boş bırakılırsa Ultralytics CUDA varsa GPU'yu, yoksa CPU'yu kullanır.

```bash
bash run.sh
```

Toplanan adayları masaüstünden gözden geçirmek için:

```bash
bash review.sh
```

Arayüz: `http://127.0.0.1:8765`. **Dosya seç** düğmesi cihazın dosya seçicisini açar. Seçilen `.pt` dosyası proje içindeki `models/` klasörüne kopyalanır ve model yolu otomatik doldurulur. Dilerseniz tam dosya yolunu elle de girebilirsiniz. Modeldeki sınıflar otomatik okunur; **Sınıfları göster** ile tekrar yükleyebilirsiniz. İşlenmesini istediğiniz sınıfları işaretleyin. Model cihazda mevcut bir Ultralytics *detection* checkpoint'i olmalı. Örnek çalışan model: `/home/waky/Projeler/ocr_project/models/license-plate-finetune-v1l.pt`. `partCheck/outputs/10091012/best_model.pt` dosyası Ultralytics checkpoint biçiminde değil.

RTSP adresini girip **Kameraya bağlan** düğmesine basın. Önizleme üzerinde çokgen ROI köşelerini sırayla tıklayın; en az üç köşe seçtikten sonra **ROI’yi tamamla** ve **Toplamaya başla** düğmelerine basın. ROI seçilmeden model çıkarımı ve aday toplama başlamaz. ROI’yi yeniden çizmek için **ROI’yi sıfırla** kullanılır.

## Kullanım

- `ffprobe` akışın H.264/H.265 codec'ini belirler. GStreamer `rtspsrc` ve yazılım çözümü ile JPEG kareleri alır.
- Çokgen ROI'nin çevrelediği bölüm kırpılır ve çokgen dışı siyaha maskelenir. Model bu görüntüyü işler; veri setine eklenecek JPEG ve YOLO koordinatları da aynı kırpıma aittir.
- Çıkarımın bulunduğu ROI kareleri belirlenen saniye aralığında otomatik olarak `pending/` klasörüne eklenir; sabit aday sınırı yoktur. Onay listesi 40'ar görsellik sayfalar halinde gösterilir. **Bu kareyi aday yap** düğmesi işlenen son ROI karesini ayrıca ekler.
- Adayda kutu seçimini değiştirebilir, **Onayla** veya **Reddet** diyebilirsiniz. Eksik/hatalı kutulu görselleri reddedin; arayüz şu aşamada yeni kutu çizmez.
- `review.sh` ile açılan masaüstü inceleme uygulaması, her adayın kutularını görüntüler. Her kutu için dahil et/çıkar seçimi yapılabilir; yanlış sınıflar seçilip sınıf listesi ya da yeni bir sınıf adıyla değiştirilebilir. **Onayla ve veri setine ekle** yalnızca dahil edilen, güncel sınıflı kutularla YOLO etiketini üretir.
- Masaüstü uygulamasındaki **Yeniden etiketlemeye gönder** düğmesi, adayın JPEG görselini ve tahmin JSON'unu veri setine eklemeden `relabel/` klasörüne taşır. Bu adaylar bekleyen listeden çıkar ve yeniden etiketleme için ayrı tutulur.
- Masaüstü uygulamasında `A` adayın mevcut düzenlemeleriyle doğrudan onaylanmasını, `R` doğrudan reddedilmesini sağlar. `1`–`9` seçili kutunun sınıfını listedeki aynı sıradaki sınıfa çevirir; örneğin `1` ilk sınıfı, `2` ikinci sınıfı atar.
- Onaylanan veriler `dataset/images/train`, `dataset/labels/train`, `dataset/classes.txt` ve `dataset/data.yaml` dosyalarında tutulur. Sınıflar model adına göre eşleştirilir; YOLO satırları `class_id x_center y_center width height` biçimindedir. Hiç kutu seçmeden onaylamak boş etiket dosyası oluşturur.
- Bekleyen adaylar uygulama yeniden başlatıldığında korunur.

## Cihaz durumu

GStreamer 1.28.7, `rtspsrc`, H.264/H.265 depay/parse, `avdec_h264`, `avdec_h265`, `videoconvert`, `jpegenc` ve `fdsink` kullanılır. `nvstreammux` yok. Mevcut PyTorch 2.5.1 CUDA derlemesi kurulu olsa da `torch.cuda.is_available()` false ve `nvidia-smi` sürücüyle haberleşemiyor. O cihazda uygulama CPU'ya düşer; CUDA olan cihazlarda GPU kullanılır.

Henüz gerçek RTSP adresi verilmediğinden canlı kameraya bağlantı doğrulanmadı.
