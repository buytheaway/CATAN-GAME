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
- [[plans/seafarers-s2a]] — maps/islands/coasts/ports и no-desert robber завершены и проверены 2026-10-09; checkpoint commit `e79dee4`. Tag optional, не блокирует development.
- [[plans/seafarers-s2b-1]] — historical completed explicit custom scenario start/bonus/capacity/VP, codec v3 и provenance, 2026-10-09; позднейшие codec/provenance статусы отмечены в плане. Existing custom presets сохранены; ограниченный Fog beta — отдельный profile ниже. S2C и более широкая competitive/player-count acceptance остаются future work.
- [[Карты и сценарии#Official Heading for New Shores — S3A]] и [[Карты и сценарии#Official The Four Islands — S3B]] — official Scenarios 1/2 реализованы на общем S2B-1 executor/ledger: точные 2021 3-/4-player layouts, edition-specific rules/provenance. S3B опубликован как `dfd6c04`; executed suites/browser/natural matches — [[Project State]]. Сценарии 3–9 и variable setup не реализованы.
- [[plans/seafarers-fog]] — foundation `0fa8f6d`, exploration `1b41360`, secure projection `dc121da`, rendering/live integration `d6f94a1`, natural checkpoint **`93439ef` published**. **Public Beta Phase 1 completed and verified; admission DISABLED BY DEFAULT**: canonical custom two-player/12 VP profile, separate admission/emergency stop, immutable beta provenance, unchanged v4 recovery/F1/receipts. Historical activation proposal preserved as superseded; broader counts/competitive/official Fog Islands remain future work. Фактические финальные проверки — [[Project State]], эксплуатация — [[Deployment#Fog beta deployment controls]].
- [[plans/persistence-auth]] — Persistence 1A/1B/1C, Auth Phase 1 и F2 safe legacy restriction завершены; profiles/history/reset и Strategy D conversion planned, не реализованы.
- [[Сервер и протокол#Private publication authorization — F1]] и [[Desktop клиент#Ship lifecycle persistence — F3]] — узкие fixes завершены; отдельные дублирующие планы не создавались.
- [[plans/plan-template]] — форма для новой крупной задачи; сначала проверить отсутствие существующего плана.

По завершении план можно сохранить как инженерную историю; актуальное состояние всегда обновляется в Project State. Не записывать переписку и ежедневные логи.
