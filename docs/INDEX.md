# Azazel Documentation Index

This index provides series-level entry points and repository-local documentation map for Azazel-Gadget (AZ-02).

## Azazel Series Positioning

Azazel-Gadget (**AZ-02**, codename `TACMOD`) is one product of the Azazel
series. Its device-class peer is
[Azazel-Edge](https://github.com/01rabbit/Azazel-Edge) (AZ-01). The full
series map, AZ designations, and naming specification live in the umbrella
repository: [01rabbit/Azazel](https://github.com/01rabbit/Azazel) ·
[Project site](https://01rabbit.github.io/Azazel/).
## Primary Documents (This Repository)

| Path | Audience | Purpose |
|---|---|---|
| [../README.md](../README.md) | Reviewer / Operator | Product overview (English) |
| [../README_ja.md](../README_ja.md) | Reviewer / Operator | Product overview (Japanese) |
| [CHANGELOG.md](CHANGELOG.md) | Reviewer / Developer | Release trace and documentation history |
| [RELEASE_PROCESS.md](RELEASE_PROCESS.md) | Maintainer | Tag/release workflow and quality gates |
| [RELEASE_NOTES_TEMPLATE.md](RELEASE_NOTES_TEMPLATE.md) | Maintainer | Standard release note template (Azazel-Edge style) |
| [DEV_LOCAL_STACK.md](DEV_LOCAL_STACK.md) | Developer | Run Gadget on macOS/dev without hardware (`bin/azazel-gadget-devstack`); EPD-on-Web (EN) |
| [DEV_LOCAL_STACK_JA.md](DEV_LOCAL_STACK_JA.md) | Developer | ハードウェア不要の開発用ローカルスタック起動手順（日本語版） |
| [SERIES_POSITIONING_AND_TERMS.md](SERIES_POSITIONING_AND_TERMS.md) | Reviewer / Developer | Series vocabulary and AZ-01/AZ-02 boundary definitions |
| [SECURITY_CLAIM_POLICY.md](SECURITY_CLAIM_POLICY.md) | Reviewer / Developer | Allowed claim boundaries and evidence requirements |
| [concepts/personal-cyber-scapegoat-gateway.md](concepts/personal-cyber-scapegoat-gateway.md) | Reviewer / Operator | AZ-02 core concept definition |
| [concepts/first-contact-surface-relocation.md](concepts/first-contact-surface-relocation.md) | Reviewer / Operator | Why first-contact relocation matters |
| [concepts/azazel-system-product-map.md](concepts/azazel-system-product-map.md) | Reviewer / Operator | AZ-01 / AZ-02 product relationship |
| [concepts/azazel-common-adapter.md](concepts/azazel-common-adapter.md) | Reviewer / Developer | Plan to serialize Gadget state/mode/action/audit/notification through the shared Azazel-Fabric (formerly Azazel-Common) `azazel-common` schema (design note, no behavior change; historical record) |
| [concepts/azazel-common-usage.md](concepts/azazel-common-usage.md) | Developer | How Gadget uses Azazel-Fabric (formerly Azazel-Common) today: the shared StatusView emit→read→surface flow and field mapping |
| [demo/submission-demo-profile.md](demo/submission-demo-profile.md) | Reviewer / Presenter | 3/7/15 minute submission demo flow |
| [demo/evidence-checklist.md](demo/evidence-checklist.md) | Reviewer / Operator | Demo verification checklist and commands |
| [presentation/README.md](presentation/README.md) | Presenter | Presentation assets map |

## Operational Notes

- Product claims must be implementation-verifiable.
- AZ-02 is a peer Azazel product, not a reduced variant of AZ-01.
- Do not describe AZ-02 as a VPN replacement or complete attack-prevention system.
