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
  ['ResumeDialog.png', ['ResumeDialog', 'MirrorEntryPaused', 'RecoverToWindow']],  // the entry page reads through it
  ['EnterDialog.png', ['MirrorEnterDialog', 'MirrorEntryNewRun']],
  ['TeamSelect.png', ['TeamSelect']],
  ['LevelWarning.png', ['LevelWarning', 'TeamSelect']],
  ['StarlightPage.png', ['StarlightPage']],
  ['StarlightConfirm.png', ['StarlightConfirm', 'StarlightPage']],
  ['StarlightConfirmConnecting.png', ['Connecting', 'StarlightConfirm', 'StarlightPage']],
  ['StartingGift.png', ['StartingGift']],
  ['StartingGiftPicked.png', ['StartingGift']],
  ['GiftGet.png', ['GiftGet']],
  ['GiftSearch.png', ['GiftSearch', 'GiftChoice']],  // same Refuse Gift button; GiftSearch comes first in the hub
  ['GiftSearchForgo.png', ['GiftSearchForgo', 'GiftSearch', 'GiftChoice']],
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
  // Battle. The forfeit screens (settings panel, Quit exploring) are read inside RouteMap's forfeit,
  // not by the hub, and the map icons still show through them.
  ['Formation.png', ['Formation']],
  ['FormationDetails.png', ['Formation']],
  ['BattleTurn.png', ['BattleTurn']],
  ['BattleTurnLit.png', ['BattleTurn']],
  ['BattleTurnSolo.png', ['BattleTurn']], // 1-sinner formation: one slot, Win Rate at x ~740
  ['BattlePause.png', ['BattlePause']],
  ['Victory.png', ['Victory']],
  ['WipeDialog.png', ['WipeDialog']],
  ['DungeonProgress.png', ['MirrorMap', 'ProgressPanel', 'RecoverToWindow']],
  ['ForfeitDialog.png', ['MirrorMap']],
  // Recovery L2 (run by Recover, not the hub): Dungeon Progress -> To Window -> Pause Exploration.
  ['ProgressPanel.png', ['MirrorMap', 'ProgressPanel', 'RecoverToWindow']],
  ['PauseExploration.png', ['MirrorMap', 'RecoverPauseConfirm']],
  ['DefeatScreen.png', ['DefeatScreen']],
  ['ExplorationComplete.png', ['ExplorationComplete']],
  // Settlement: the summary behind the window still reads; Settle handles the window's own dialogs.
  ['RunVictory.png', ['RunVictory']],
  ['ExplorationReward.png', ['ExplorationReward', 'ExplorationComplete']],
  ['ExplorationRewardOff.png', ['ExplorationReward', 'ExplorationComplete']],
  ['GiveUpDialog.png', ['ExplorationReward', 'ExplorationComplete']],
  ['ClaimNoBonusDialog.png', ['ExplorationReward', 'ExplorationComplete']],
  // Rewards and events. The dialogs sit over their page, which still reads.
  ['RewardCard.png', ['RewardCard']],
  ['RewardCardForgo.png', ['RewardCardForgo', 'RewardCard']],
  ['GiftChoice.png', ['GiftChoice']],
  ['BossGiftTrials.png', ['GiftChoice']],
  ['BossGiftTrialsHard.png', ['GiftChoice']],
  ['GiftRefuseDialog.png', ['GiftRefuseDialog', 'GiftChoice']],
  ['EventStory.png', ['Event']],
  ['EventChoices.png', ['Event']],
  ['EventCheck.png', ['Event']],
  ['EventResult.png', ['Event']],
  // Shop: Leave stays readable under the shop's own dialogs and pages; the heal page has Return instead.
  ['Shop.png', ['Shop']],
  ['SuperShop.png', ['Shop']],
  ['ShopPurchase.png', ['Shop']],
  ['ShopFuse.png', ['Shop']],
  ['ShopHeal.png', []],
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
