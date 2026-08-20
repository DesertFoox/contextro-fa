# Contextro FA

پروژه دانشگاهی پردازش زبان طبیعی فارسی (NLP) برای تحلیل شباهت معنایی کلمات و بازی حدس کلمه به سبک Contexto.

## اجرای سریع

پیش‌نیاز: **Python 3.11 یا بالاتر**.

در ویندوز فقط فایل `start.bat` را اجرا کنید. برنامه بدون Docker، Node.js، npm، pip install یا دانلود مدل، به‌صورت آفلاین روی `http://127.0.0.1:8000` اجرا می‌شود.

`start.bat` ابتدا دیتاست کامل معنایی V3 را به‌صورت آفلاین از 6 بخش فشرده داخل `backend/app/data/semantic_bundle/` بازسازی می‌کند و بعد سرور بازی را بالا می‌آورد. فایل بازسازی‌شده همان دیتاست 165 هدفی نسخه نهایی پروژه است.

## رابط کاربری نهایی

رابط کاربری نهایی V3 که با `start.bat` اجرا می‌شود داخل مسیر زیر قرار دارد:

`backend/app/static/`

- `index.html` ساختار رابط کاربری
- `app.js` منطق بازی و ارتباط با API
- `styles.css` ظاهر RTL فارسی

این نسخه شامل Hint، Next Word، Give Up، Share Result، Score/Streak، Semantic Journey، Top Semantic Neighbors و AI Lab است.

> برای جلوگیری از سردرگمی، React scaffold قدیمی از مخزن تحویلی حذف شده است. نسخه قابل ارزیابی و نهایی همان UI آفلاین بالا است.

## قابلیت‌ها

- Semantic Similarity و Ranking فارسی
- 1,233 واژه فارسی در فضای رتبه‌بندی
- 165 کلمه هدف
- 28 حوزه معنایی و 84 زیرحوزه
- روابط معنایی وزن‌دار و Cross-domain relations
- Hint چندمرحله‌ای
- Semantic Journey
- نمایش نزدیک‌ترین واژه‌ها بعد از حل
- Score و Streak بین راندها
- Give Up و Next Word
- Share Result بدون لو دادن جواب
- AI Lab و benchmark داخلی
- مسیر پژوهشی برای Fine-tuning مدل Transformer

## موتور Semantic

نسخه آفلاین برای اینکه روی سیستم استاد سریع اجرا شود، در زمان اجرا به PyTorch یا Hugging Face وابسته نیست. موتور از ترکیب موارد زیر برای رتبه‌بندی استفاده می‌کند:

1. Persian Semantic Ontology
2. روابط معنایی وزن‌دار
3. Sparse Semantic Vector
4. Cross-domain relations
5. شباهت املایی سبک برای غلط‌های تایپی
6. Rank در کل vocabulary

امتیاز نمایش‌داده‌شده **Probability نیست**؛ یک Proximity Score کالیبره‌شده برای تجربه بازی است.

## ساختار اصلی

```text
contextro-fa/
├── start.bat
├── README.md
├── README-RUN.md
└── backend/
    ├── prepare_semantic_data.py   # Rebuild exact V3 semantic dataset offline
    ├── lightweight_server.py
    ├── app/
    │   ├── static/                # Final V3 UI
    │   └── data/
    │       ├── semantic_bundle/   # Exact compressed final dataset
    │       ├── semantic_ontology.json
    │       ├── cross_relations.csv
    │       ├── vocabulary.txt
    │       └── daily_words.txt
    └── training/                  # Benchmark and research/training assets
```

## Benchmark

Benchmark داخلی پروژه روی 10 سناریوی semantic sanity-check، **97.5% Pairwise Semantic Ordering** ثبت کرده است. این عدد accuracy عمومی زبان فارسی نیست و فقط بررسی می‌کند که در تست‌های تعریف‌شده، واژه مرتبط بالاتر از واژه نامرتبط rank شود.

## هدف دانشگاهی

هدف پروژه نمایش یک pipeline کامل برای ساخت فضای معنایی فارسی، رتبه‌بندی واژگان، طراحی بازی NLP، پیاده‌سازی API، ارزیابی داخلی و فراهم‌کردن مسیر Fine-tuning مدل Transformer است؛ در عین حال نسخه ارائه طوری طراحی شده که استاد بتواند با یک `start.bat` آن را آفلاین اجرا کند.
