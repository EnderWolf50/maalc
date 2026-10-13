import type { FullConfig } from '@nekosu/maa-tools'

const config: FullConfig = {
  cwd: import.meta.dirname,
  maaVersion: '5.14.3',
  interfacePath: 'assets/interface.json',
  check: {},
  test: {
    // Screen-node cases (07-assets-and-testing.md) land here with the first templates.
    cases: [],
  },
}

export default config
