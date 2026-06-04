# VSDD ワークフロー — Skills Detail

> 各 VSDD Skill の入出力・引数・呼出エージェント・連携先を詳細化したリファレンス。
> 概念は [vsdd-workflow.md](./vsdd-workflow.md)、使い方は [vsdd-workflow-usage.md](./vsdd-workflow-usage.md)。

---

## /vsdd-steering （Phase 0）

| 項目                 | 内容                                                                        |
| -------------------- | --------------------------------------------------------------------------- |
| **役割**             | プロジェクトのステアリング 4 ファイル（`_steering/`）を bootstrap / refresh |
| **引数**             | `[--force] [--dry-run]`                                                     |
| **入力**             | `package.json`, `src/features/**`, `.claude/rules/typescript/*`             |
| **出力**             | `.claude/specs/_steering/{tech,structure,context,open-questions}.md`        |
| **呼出エージェント** | なし（純粋な自動抽出）                                                      |
| **呼出先 Skill**     | なし                                                                        |
| **呼出元 Skill**     | `/vsdd-init` Step 0                                                          |
| **承認ゲート**       | 新規 Q-XXX 0 件 → 続行、≥ 1 件 → 中断（呼出元判定）                         |

### 検出ルール

| ID  | 検出内容                                                             |
| --- | -------------------------------------------------------------------- |
| 1   | 用語衝突（同一語幹が複数 feature にまたがる）                        |
| 2   | 未使用シンボル（`pnpm fallow:dead-code` 取込）                       |
| 3   | version 不整合（`package.json` major と `.claude/rules` の記述差異） |
| 6   | 責務不明 feature（`types/` `schemas/` 空）                           |

---

## /vsdd-init （Phase 1）

| 項目                 | 内容                                                                                   |
| -------------------- | -------------------------------------------------------------------------------------- |
| **役割**             | spec ディレクトリ初期化                                                                |
| **引数**             | `<slug> [notion-url] [--mode standard\|auto]`                                          |
| **入力**             | Notion URL (オプション), `_steering/`（Step 0 で `/vsdd-steering` 経由）                |
| **出力**             | `.claude/specs/<slug>/{source-notion.md, progress.md, change-log.md}` + プレースホルダ |
| **呼出エージェント** | なし                                                                                   |
| **呼出先 Skill**     | `/vsdd-steering`（Step 0 内部呼出）                                                     |
| **承認ゲート**       | `CONFIRM vsdd-requirements`                                                             |

### Step 0 の Gate ロジック

- `_steering/open-questions.md` の新規 Q-XXX 検出件数を読む
- 0 件 → Step 1 へ
- ≥ 1 件 → 中断、ユーザに grill or `dismiss <Q-id>` を促す

---

## /vsdd-requirements （Phase 2）

| 項目                 | 内容                                                                       |
| -------------------- | -------------------------------------------------------------------------- |
| **役割**             | EARS 形式の要件（REQ-001..N）作成                                          |
| **引数**             | `<slug>`                                                                   |
| **入力**             | `source-notion.md` (任意), `_steering/context.md` (用語強制)               |
| **出力**             | `.claude/specs/<slug>/requirements.md`                                     |
| **呼出エージェント** | なし（テンプレート + AI ドラフト）                                         |
| **承認ゲート**       | `CONFIRM vsdd-review-requirements`                                          |
| **モード差**         | `standard`: 人間が REQ を埋める / `auto`: 7 問のヒアリング後 AI が一括作成 |

### Step 0: Steering Load

- `context.md` の登録用語のみ使用
- 未登録語が必要な場合: `open-questions.md` に Q-XXX 追加 + REQ に `> **Glossary pending**: <term>` 注記

---

## /vsdd-review-requirements （Phase 3）

| 項目                            | 内容                                                                         |
| ------------------------------- | ---------------------------------------------------------------------------- |
| **役割**                        | requirements.md のレビュー                                                   |
| **引数**                        | `<slug>`                                                                     |
| **入力**                        | `requirements.md`, `_steering/context.md`                                    |
| **出力**                        | `review-results/requirement-review.md`                                       |
| **呼出エージェント (standard)** | `requirements-analyst` → `ecc:planner` → `ecc:docs-lookup` → `ecc:architect` |
| **呼出エージェント (auto)**     | `requirements-analyst` のみ                                                  |
| **承認ゲート**                  | `CONFIRM vsdd-design`                                                         |

### チェック項目

| ID    | 内容                             | 重大度          |
| ----- | -------------------------------- | --------------- |
| 1     | EARS Format Compliance           | HIGH/MEDIUM     |
| 2     | Ambiguous Terms                  | MEDIUM          |
| 3     | Missing Elements                 | HIGH/MEDIUM     |
| 4     | Testability                      | HIGH/MEDIUM     |
| 5     | Completeness                     | MEDIUM/HIGH/LOW |
| 6     | REQ ID Numbering                 | LOW/HIGH        |
| 7     | Technical Feasibility (standard) | HIGH/MEDIUM     |
| **8** | **Term Drift against Steering**  | **HIGH/MEDIUM** |

Check 8 は `context.md` 未登録の用語使用 / 登録済 vs 使用文脈の意味乖離を検出。

---

## /vsdd-design （Phase 4）

| 項目           | 内容                                                                        |
| -------------- | --------------------------------------------------------------------------- |
| **役割**       | Mermaid 図 + ファイル構造 + 状態管理方針                                    |
| **引数**       | `<slug>`                                                                    |
| **入力**       | `requirements.md`, `_steering/{structure,tech,context}.md`, `docs/adr/*.md` |
| **出力**       | `.claude/specs/<slug>/design.md`                                            |
| **呼出先**     | `/ecc:plan` (command)                                                       |
| **承認ゲート** | `CONFIRM vsdd-tasks`                                                         |

### Step 0: Steering Load

- `structure.md` の feature 境界を遵守。新規 feature は追加可だが境界を逸脱しない
- `tech.md` 掲載ライブラリのみ使用。新規ライブラリは ADR で正当化
- 横断決定は `Satisfies: ADR-NNNN` で引用
- 新規アーキ決定は `> **ADR candidate**: <rationale>` でフラグ → 後で ADR 化

---

## /vsdd-tasks （Phase 5）

| 項目                 | 内容                             |
| -------------------- | -------------------------------- |
| **役割**             | 設計を TDD 順 TASK-001..M に分解 |
| **引数**             | `<slug>`                         |
| **入力**             | `design.md`, `requirements.md`   |
| **出力**             | `tasks.md`, `progress.md` 更新   |
| **呼出エージェント** | `ecc:planner` (推奨)             |
| **承認ゲート**       | `CONFIRM vsdd-review-plan`        |

各 TASK は `Implements: REQ-XXX` と `Design ref: §X.X` を必須記載。

---

## /vsdd-review-plan （Phase 6）

| 項目                            | 内容                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| **役割**                        | REQ → 設計 → タスクのトレーサビリティ検証                                             |
| **引数**                        | `<slug>`                                                                              |
| **入力**                        | `requirements.md`, `design.md`, `tasks.md`, `_steering/structure.md`, `docs/adr/*.md` |
| **出力**                        | `review-results/plan-review.md`                                                       |
| **呼出エージェント (standard)** | `ecc:docs-lookup` → `ecc:planner` → `ecc:architect`                                   |
| **呼出エージェント (auto)**     | `ecc:architect` のみ                                                                  |
| **承認ゲート**                  | 全 8 チェック ✅ → `CONFIRM vsdd-impl`                                                 |

### トレーサビリティチェック

| ID    | 内容                                                                |
| ----- | ------------------------------------------------------------------- |
| A     | REQ → Design coverage                                               |
| B     | REQ → Task coverage                                                 |
| C     | Design → Task coverage                                              |
| D     | Task → REQ completeness                                             |
| E     | Dangling references                                                 |
| F     | Duplicate IDs                                                       |
| **G** | **Structure Adherence**（`design.md` のパスが `structure.md` 整合） |
| **H** | **ADR Citation**（横断決定が ADR 引用 or `> **ADR candidate**`）    |

いずれか ❌ で実装ブロック。

---

## /vsdd-impl （Phase 7）

| 項目             | 内容                                                                                          |
| ---------------- | --------------------------------------------------------------------------------------------- |
| **役割**         | TDD 実装、`feat(TASK-NNN):` 形式でコミット                                                    |
| **引数**         | `<slug> [task-id]` (省略時は全 pending タスク連続実行)                                        |
| **入力**         | `tasks.md`, `design.md`, `requirements.md`                                                    |
| **出力**         | コード + テスト, `progress.md` 更新                                                           |
| **呼出先 Skill** | `/ecc:tdd-workflow`                                                                           |
| **承認ゲート**   | `CONFIRM vsdd-review`                                                                          |
| **モード差**     | `standard`: Red/Green/Refactor 各段階で停止 / `auto`: 連続実行、check 失敗時最大 3 回自己修正 |

---

## /vsdd-review （Phase 8）

| 項目           | 内容                                                                                      |
| -------------- | ----------------------------------------------------------------------------------------- |
| **役割**       | コード + セキュリティ + ステアリング drift レビュー                                       |
| **引数**       | `<slug>`                                                                                  |
| **入力**       | `git diff main...HEAD`, `requirements.md`, `tasks.md`, `_steering/*`                      |
| **出力**       | `review-results/code-review.md`                                                           |
| **呼出先**     | native `code-review` (skill), `/ecc:code-review` (command), `ecc:security-review` (skill) |
| **承認ゲート** | CRITICAL 0 件で `CONFIRM vsdd-pr`                                                          |

### Step 4.5: Steering Drift Check

| 検査             | 内容                                           |
| ---------------- | ---------------------------------------------- |
| 新規 feature     | `structure.md` に記載されているか              |
| 新規 export      | `structure.md` の feature 行に列挙されているか |
| 新規ドメイン用語 | `context.md` に登録されているか                |
| 新規 dep         | `tech.md` に記載されているか                   |
| 横断アーキ変更   | ADR 引用 or `> **ADR candidate**` フラグあり   |

drift 検出時は `## Steering Drift` セクションに MEDIUM (or HIGH) で記録。

---

## /vsdd-pr （Phase 9）

| 項目           | 内容                                                        |
| -------------- | ----------------------------------------------------------- |
| **役割**       | REQ → TASK → commit トレーサビリティ表付きの GitHub PR 作成 |
| **引数**       | `<slug>`                                                    |
| **入力**       | `tasks.md`, `requirements.md`, `change-log.md`, `git log`   |
| **出力**       | GitHub PR (`gh pr create` 経由)                             |
| **承認ゲート** | なし（最終フェーズ）                                        |

---

## /vsdd-workflow （Meta）

| 項目           | 内容                           |
| -------------- | ------------------------------ |
| **役割**       | フェーズ進捗の表示 (read-only) |
| **引数**       | `[slug]` (省略時は全 spec)     |
| **入力**       | `progress.md`                  |
| **出力**       | stdout のみ                    |
| **承認ゲート** | なし                           |

---

## 補助ツール一覧（Agent / Skill / Command）

| ツール                 | 種別    | 用途                     | 起動 Phase           |
| ---------------------- | ------- | ------------------------ | -------------------- |
| `requirements-analyst` | agent   | EARS 整形 / 曖昧表現検出 | 3                    |
| `ecc:docs-lookup`      | agent   | スタックドキュメント収集 | 3, 6 (standard のみ) |
| `ecc:planner`          | agent   | スコープ / 依存リスク    | 3, 5, 6              |
| `ecc:architect`        | agent   | 技術的実現可能性         | 3, 6 (standard のみ) |
| `/ecc:plan`            | command | アーキテクチャ設計委譲   | 4                    |
| `ecc:tdd-workflow`     | skill   | TDD 実装ループ           | 7                    |
| `/ecc:code-review`     | command | 7 カテゴリ体系的レビュー | 8                    |
| `ecc:security-review`  | skill   | セキュリティ観点         | 8                    |

---

## 参考リンク

- [VSDD ワークフロー（概念ガイド）](./vsdd-workflow.md)
- [Usage Guide（使い方）](./vsdd-workflow-usage.md)
- [VSDD ワークフロー インタラクティブ図](./vsdd-workflow.html)
