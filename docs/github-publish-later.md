# Later: public GitHub publish

Canonical development is **Forgejo** (`coreyhines/acta`).
GitHub `bjbyrnesy/ACT-Automation` is a transition mirror.

When ready to publish publicly:

1. Create (or rename) the public GitHub repository.
2. From a clone whose `origin` is Forgejo:

   ```bash
   git remote add public git@github.com:<org-or-user>/<public-name>.git
   git push public --all
   git push public --tags
   ```

3. Point README clone URLs / badges at the public GitHub repo (keep Forgejo as
   the internal canonical, or flip if you want GitHub-first after launch).
4. Archive or mark `bjbyrnesy/ACT-Automation` as moved/mirror if the name changes.
5. Optional: configure Forgejo → GitHub push mirror for `main` only.

Until then, keep the `github` remote and occasionally:

```bash
git push github main
```
