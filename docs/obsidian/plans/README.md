---
tags: [catan, планы]
---

# Engineering plans

[[00 Главная]] · [[Project State]] · [[Documentation Policy]]

Крупная задача имеет отдельный план с целью, областью, инвариантами, шагами и проверкой. План не является разрешением на изменение кода. Начать исполнение можно только в рамках соответствующей задачи пользователя.

- [[plans/server-authority-hardening]] — Phase 1 завершена 2026-10-03 после исходных проверок 2026-10-02; оставшиеся ограничения указаны в плане.
- [[plans/web-ui-redesign]] — исторический первоначальный Draft/reference plan; текущую реализацию описывает [[plans/game-ui-redesign]].
- [[plans/game-ui-redesign]] — Game UI Phases 1/2, Room UX 2.1–2.3 и Product Polish Phases 1–4 завершены в своём scope, включая audio; future mobile/accessibility/load work явно отделены.
- [[plans/containerization]] — Production Infrastructure Phase 1 Completed, 2026-10-04; эксплуатационные инструкции — [[Deployment]].
- [[plans/board3d]] — Phases 1–3/polish и terrain/building GLB integration завершены. Default 3D и SVG используют один snapshot/controller; interactive renderer не исполняет правила.
- [[plans/seafarers-s1]] — historical completed S1, проверен 2026-10-08; S1/F1/F2/F3 checkpoint `seafarers-hardening-s1` → `b5cc066`.
- [[plans/seafarers-s2a]] — maps/islands/coasts/ports и no-desert robber завершены и проверены 2026-10-09, READY FOR CHECKPOINT; без автоматического commit/tag. S2B/S2C/S3 planned, не начаты.
- [[plans/persistence-auth]] — Persistence 1A/1B/1C, Auth Phase 1 и F2 safe legacy restriction завершены; profiles/history/reset и Strategy D conversion planned, не реализованы.
- [[Сервер и протокол#Private publication authorization — F1]] и [[Desktop клиент#Ship lifecycle persistence — F3]] — узкие fixes завершены; отдельные дублирующие планы не создавались.
- [[plans/plan-template]] — форма для новой крупной задачи; сначала проверить отсутствие существующего плана.

По завершении план можно сохранить как инженерную историю; актуальное состояние всегда обновляется в Project State. Не записывать переписку и ежедневные логи.
