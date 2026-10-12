# 06 — בדיקות

מסגרת: `pytest`. הרצה: `python -m pytest tests -q`.

## מקרי חובה לפי פיצ'ר

| פיצ'ר | בדיקה |
|---|---|
| F1 | הרשמה יוצרת UserRegistered; התחברות נכשלת בסיסמה שגויה; מועמד לא ניגש לדשבורד HR |
| F2 | HR יוצר Draft; רק HiringManager פותח משרה |
| F3 | חיפוש מחזיר משרה פתוחה לפי מילת מפתח |
| F4 | הגשה יוצרת ApplicationSubmitted ומעלה applicant_count |
| F5 | דשבורד סופר משרות Open ונרשמים |
| F6 | הטמעת שני CV שונים מחזירה דירוג סמנטי |
| F7 | worker על מועמדות Submitted מייצר ScreeningCompleted עם ציון |
| F8 | Reject משנה סטטוס ונרשם אירוע |

## בדיקות ארכיטקטורה

- Command כותב ל-`events` לפני עדכון פרויקציה.
- Query לא קורא ל-`event_store.append`.
- אין מחרוזות נושא-טיסות בקוד המוצר (`app/`, `templates/`).
