# CATAN design references

Оригинальные PNG из сообщения пользователя, просмотрены 2026-10-01. Сохранены побайтово без resize, обрезки, перекодирования или иных изменений. Все оригиналы имеют разрешение 1672 × 941; это metadata файлов, а не требуемый размер UI.

| Файл | Назначение | Вложение в сообщении |
| --- | --- | --- |
| [gameplay-concept.png](gameplay-concept.png) | Матч: карта в центре, игроки слева, личная рука справа, нижние действия | 5; вложение 6 — побайтовый повтор |
| [lobby-concept.png](lobby-concept.png) | Составной main menu / lobby с участниками, сценариями, chat и запуском | 4 |
| [modals-concept.png](modals-concept.png) | Коллекция Trade, Build, Development, Discard, Robber, Victory, Toasts, Leave | 3 |
| [settings-concept.png](settings-concept.png) | General Settings, sidebar категорий и grouped controls | 1 |
| [rules-help-concept.png](rules-help-concept.png) | Иллюстрированные правила Base Game / Seafarers и краткая памятка | 2 |
| [gameplay-concept-alt.png](gameplay-concept-alt.png) | Второй вариант матча: счётчики фигур справа и подсказка Your turn в action bar | 7 |

Второй уникальный gameplay сохранён отдельно. Повтор вложения 6 не создаёт ещё один идентичный файл. Оба игровых варианта остаются references; окончательный вариант не выбран.

Наблюдения, UX-интерпретации, статус concepts и TBD находятся в [Design System](../../obsidian/Design%20System.md). Эта папка хранит оригиналы, а не второй дизайн-справочник.

**Design mockups are references, not final implementation specifications.** Надписи и числа не устанавливают gameplay-правила. Наличие controls не означает готовую backend-функцию. Изображения не являются pixel-perfect заданием.

## Original-byte verification

SHA-256 сохранённых файлов сверены с исходными PNG-байтами вложений:

```text
gameplay-concept.png      e269ef65287bfcee5220c3ff25a911190cbb40d08ff9c45c6ab644481fe00dea
lobby-concept.png         bf4099fd035fa7c01368e111010a27ced9a0db2e8dfdc8c86d37ab3de6a3eb55
modals-concept.png        6ec57ae87e13fda66d1f51344d718ff54aab149d55a669cd243307f6a66a58d5
settings-concept.png      40862721bf99d4cf8ab4cb6b4a2d9c1ae6b4ff0434634e9b83d983006c17e7bf
rules-help-concept.png    804957288975f06d8f56cbc7d63314a096a6e0ef33bfe5b65ce16d011fef5856
gameplay-concept-alt.png  a4ce007b400c6c0e2073204fe3c6cce60e0e9265b00c11b9e4ae892b7b5857a2
```
