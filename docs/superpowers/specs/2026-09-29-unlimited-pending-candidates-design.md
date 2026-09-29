# Sınırsız Bekleyen Aday Toplama

## Amaç

Otomatik aday toplama, bekleyen aday sayısı 500'e ulaştığında durmamalıdır.

## Tasarım

- Çıkarım döngüsündeki `len(store.list()) < 500` kontrolü kaldırılacaktır.
- Tespit içeren her uygun kare, `collect_interval` süresine göre `pending/` dizinine eklenecektir.
- 500 aday sınırına ilişkin hata mesajı kaldırılacaktır.
- Uygulama için yazılımsal aday kotası olmayacaktır; kullanılabilir disk alanı doğal operasyonel sınırdır.

## Etki Alanı

Yalnızca `Labeller._infer_loop` içindeki otomatik aday oluşturma koşulu değişecektir. Elle aday oluşturma, onay, red ve veri setine aktarma davranışları değişmez.

## Doğrulama

Bir regresyon testi, depoda 500 aday varmış gibi raporlansa bile tespitli bir sonucun otomatik olarak eklendiğini doğrulayacaktır. Mevcut Python derleme denetimi de çalıştırılacaktır.
