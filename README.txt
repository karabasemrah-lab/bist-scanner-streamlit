BIST Scanner Streamlit v0.8
===========================

v0.8 değişiklikleri:
- Tarama motorlarına dokunulmadı; v0.7 analiz mantığı korunmuştur.
- Fusion Excel ana sayfası artık ekranda gösterilen/filtrelenen sonuçları içerir.
- Trend Devam Excel ana sayfası yalnızca Devam Kırılımı sonuçlarını içerir.
- Excel sütun başlıkları Türkçeleştirildi ve sadeleştirildi.
- Otomatik sütun genişliği, filtre, sabit başlık satırı ve sayı biçimlendirmesi eklendi.
- İkinci sayfada "Tüm Analiz" ham analiz sonuçları korunur.
- Veri alınamayan/işlenemeyen hisseler varsa "İşlenemeyenler" sayfasına eklenir.
- TradingView hisse bağlantıları ve paralel tarama yapısı korunmuştur.

Çalıştırma:
python -m streamlit run streamlit_app.py
