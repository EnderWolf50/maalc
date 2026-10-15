import type { FullConfig } from '@nekosu/maa-tools'

// Every image runs every node named below; a node not in its hits must miss (07-assets-and-testing.md).
const screens: [image: string, hits: string[]][] = [
  ['Title.png', ['GoToMirrorEntry', 'NavTitle']],
  ['TitleConnecting.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['TitleFading.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['Loading.png', ['Loading']],
  ['MainWindow.png', ['GoToMirrorEntry', 'NavMainTabs']],
  ['MainWindowFadeIn.png', ['GoToMirrorEntry', 'NavMainTabs']],
  ['SinnersTab.png', ['GoToMirrorEntry', 'NavMainTabs']],
  ['Drive.png', ['GoToMirrorEntry', 'NavDrive']],
  ['EntryNewRun.png', ['MirrorEntryNewRun']],
  ['EntryPaused.png', ['MirrorEntryPaused']],
  ['EnterDialog.png', ['MirrorEnterDialog', 'MirrorEntryNewRun']],
  ['TeamSelect.png', ['TeamSelect']],
  ['LevelWarning.png', ['LevelWarning', 'TeamSelect']],
  ['StarlightPage.png', ['StarlightPage']],
  ['StarlightConfirm.png', ['StarlightConfirm', 'StarlightPage']],
  ['StarlightConfirmConnecting.png', ['Connecting', 'StarlightConfirm', 'StarlightPage']],
  ['StartingGift.png', ['StartingGift']],
  ['StartingGiftPicked.png', ['StartingGift']],
  ['GiftGet.png', ['GiftGet']],
  ['GiftSearch.png', ['GiftSearch']],
  ['GiftSearchForgo.png', ['GiftSearchForgo', 'GiftSearch']],
  ['ThemePack.png', ['ThemePack']],
  ['ThemePackNormal.png', ['ThemePack']],
  ['MirrorMap.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeEvent']],
  // Map marks: the default ROIs fit a map at rest; RouteMap moves them with the bus.
  ['MapEvent.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeEvent']],
  ['MapFocused.png', ['MirrorMap', 'MapBus', 'MapLinkMid', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedHex']],
  ['MapPanned.png', ['MirrorMap', 'MapBus', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedHex', 'MapNodeEvent']],
  ['MapRock.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedRound', 'MapNodeEvent']],
  ['MapCards.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedRound', 'MapNodeEvent']],
  ['MapShop.png', ['MirrorMap', 'MapBus', 'MapLinkDown', 'MapNodeShop']],
  ['MapBoss.png', ['MirrorMap', 'MapBus', 'MapLinkMid', 'MapNodeCost', 'MapNodeGift', 'MapNodeBoss']],
  ['MapNodePanel.png', ['MapNodePanel']],
]

const config: FullConfig = {
  cwd: import.meta.dirname,
  maaVersion: '5.14.3',
  maaLogDir: 'debug',
  interfacePath: 'assets/interface.json',
  check: {},
  test: {
    cases: [
      {
        configs: { controller: 'MuMu', resource: 'base', imageRoot: 'tests/screens' },
        cases: screens.map(([image, hits]) => ({ image, hits })),
      },
    ],
  },
}

export default config
