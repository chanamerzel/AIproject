# הנחיות לסוכן הקוד — FitScreen

קרא לפני כל שינוי:

1. `docs/00-vision.md` — התחום הוא גיוס בלבד.
2. `docs/04-features.md` — עבוד על פיצ'ר שלם, לא על מחלקה בודדת.
3. `.cursor/rules/sdad.mdc` — CQRS ו-Event Sourcing.

אסור:

- לכתוב ישירות לטבלאות query בלי אירוע.
- לערבב Command ו-Query באותו מודול.
- להוסיף שפת טיסות / כרטיסים / חדשות כתחום מוצר.

חובה:

- כל כתיבה עסקית: Command → `EventStore.append` → Projection.
- בדיקה לפי `docs/06-testing.md` אחרי פיצ'ר.
- הרשאות לפי תפקיד ב-views.
