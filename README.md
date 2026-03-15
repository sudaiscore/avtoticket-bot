# AvtoTicket Monitoring Bot (Production Ready)

AvtoTicket saytidan ma'lum bir yo'nalish bo'yicha chiptalarni avtomatik ravishda kuzatib boradigan va bo'sh joy ochilganda foydalanuvchiga Telegram orqali xabar beradigan qulay, tezkor va barqaror asinxron Python boti.

## 🔥 Asosiy Qulayliklar
- **Aqlli Filtrlash:** Chipta qidirayotgan yo'nalishingiz qat'iy tekshiriladi (`Toshkent ➡️ Shahrisabz`). Xato va teskari reyslar sizni bezovta qilmaydi.
- **O'zgarishlarni Guruhlash va Farqlash:**
    - 🆕 **Yangi:** Mutlaqo yangi reys qo'shilsa xabar beradi.
    - 🔓 **Ochildi:** Oldin joyi yo'q (0 ta) bo'lgan reysda joy ochilsa xabar beradi.
    - 📈 **Oshdi:** Mavjud reysda qo'shimcha joylar tashlanganda (`2 ta ➡️ 5 ta`) xabar beradi.
- **Mukammal Telegram UX:** HTML taglari kesilib ketishidan himoyalangan xavfsiz uzunlik boshqaruvi. Eng ko'p joyi bor va vaqti erta reyslar eng yuqorida ko'rinadi.
- **Atomik Saqlash:** Bot vaqtincha to'xtab qolsa ham ishlagan joyidan davom etadi (`state.json` atomik yoziladi). Bir xil reys uchun takroriy xabarlar jo'natilmaydi.

## 🛠 O'rnatish bo'yicha yo'riqnoma

1. Loyiha nusxasini oling va loyiha papkasida Python virtual muhitini yarating (Python 3.11+ tavsiya qilinadi):
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux / macOS
   venv\Scripts\activate         # Windows