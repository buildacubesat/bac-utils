# Contributing to bac-utils

Thanks for contributing to Build a CubeSat. Open an issue before larger changes so the direction can be agreed first; small fixes can go straight to a pull request against `main`. The conventions every BAC repository follows are in the [BAC Project & Tooling Guide](https://github.com/buildacubesat/bac-design/blob/main/guides/bac-project-and-tooling-guide.md).

## 1. Developer Certificate of Origin

BAC asks for no contributor license agreement. Instead, every commit is signed off under the [Developer Certificate of Origin](https://developercertificate.org/) (DCO): by signing off you certify that you wrote the change, or otherwise have the right to submit it under this repository's license, and that the contribution and your sign-off are kept on public record.

Sign off each commit:

```sh
git commit -s
```

This adds a line such as `Signed-off-by: Ada Lovelace <ada@example.org>` from your `user.name` and `user.email`. The address has to match the commit's author address. Signing off is not the same as signing a commit with a GPG or SSH key – it needs no key.

- You keep the copyright in your contribution.
- Your contribution is licensed under the MIT License (see `LICENSE`) – the same license everyone receives it under. Nothing is relicensed, and there is nothing else to sign.
- A check on every pull request fails if a commit has no sign-off matching its author. To sign off a branch you already pushed, run `git rebase --signoff <base>` with the branch you opened the pull request against (for example `upstream/main`), then `git push --force-with-lease`. For the last commit alone, `git commit --amend -s --no-edit` is enough.

## 2. Code of Conduct

Everyone in BAC's spaces follows the [BAC Code of Conduct](https://bac.page/conduct). Report a possible violation to conduct@buildacubesat.space.
