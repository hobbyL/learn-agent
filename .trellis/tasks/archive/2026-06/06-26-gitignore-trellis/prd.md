# 将工具配置目录从 git 追踪中移除并加入 gitignore

## Goal

将 `.trellis/`、`.claude/`、`.codex/`、`.agents/`、`AGENTS.md` 从 git 追踪中彻底移除，
并加入 `.gitignore`，使其不再出现在 `git status` 中。

## Requirements

- 在 `.gitignore` 末尾追加以下条目：
  - `.trellis/`
  - `.claude/`
  - `.codex/`
  - `.agents/`
  - `AGENTS.md`
- 对已被 git 追踪的文件执行 `git rm --cached -r`，使其退出追踪但本地文件保留
- 已追踪的路径：`.trellis/`（有多个文件已提交）
- `.claude/`、`.codex/`、`.agents/`、`AGENTS.md` 目前是 untracked，只需加 gitignore 即可

## Acceptance Criteria

- [ ] `git status` 中不再出现 `.trellis/`、`.claude/`、`.codex/`、`.agents/`、`AGENTS.md`
- [ ] 本地目录文件仍然存在（`ls .trellis/` 有内容）
- [ ] `.gitignore` 包含上述五条规则

## Out of Scope

- 不修改任何项目代码
- 不删除本地文件

## Technical Notes

- `.trellis/` 已有提交记录，必须 `git rm --cached -r .trellis/`
- 其余目录/文件是 untracked，加 gitignore 即可
