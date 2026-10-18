import { availableParallelism } from 'node:os'
import type { FullConfig } from '@nekosu/maa-tools'

// Every image runs every node named below; a node not in its hits must miss (07-assets-and-testing.md).
const screens: [image: string, hits: string[]][] = [
  ['Title.png', ['GoToMirrorEntry', 'NavTitle']],
  ['TitleConnecting.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['TitleFading.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['Loading.png', ['Loading']],
  ['MaintenanceNotice.png', ['MaintenanceNotice', 'PopupButton', 'GoToMirrorEntry', 'NavTitle']],  // live 2026-10-15, over the title
  // Synthetic (#83): EventStory with the notice's message line pasted into its text box. Only the
  // notice window stops the task, not the word in other text.
  ['EventMaintenanceText.png', ['Event']],
  // Synthetic (#86), no live capture yet: the one-button notice window (live) as the title's dialogs. The
  // download dialog (live 2026-10-16: `Downloading N MB of data`, Close / Confirm; the layout is a guess)
  // is Confirmed; a one-button error box is closed by its one button. Both sit on the title, which reads through.
  ['TitleDownload.png', ['DownloadDialog', 'GoToMirrorEntry', 'NavTitle']],
  ['TitleErrorConfirm.png', ['PopupButton', 'GoToMirrorEntry', 'NavTitle']],
  // Synthetic (#84), no live capture yet: the one-button notice window (MaintenanceNotice's, live) relabelled
  // as a server error with a countdown Retry or a Try Again button. They put RetryPopup on every other screen.
  ['RetryCountdown.png', ['RetryPopup', 'GoToMirrorEntry', 'NavTitle']],
  ['TryAgain.png', ['RetryPopup', 'GoToMirrorEntry', 'NavTitle']],
  // The Parallel Superposition prompt after clearing floor 5 / 10 with the mode engaged (#85). Captured from the
  // game's own help sheet (the page behind it is the help text, not a map): the dialog is its live look, but where
  // it sits on screen is not confirmed. A Cancel / Confirm question, so PopupButton (one centred button) stays out.
  ['ParallelModePrompt.png', ['ParallelModePrompt']],
  ['ParallelModeExtreme.png', ['ParallelModePrompt']],
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
  ['StartingGiftSearchOff.png', ['StartingGift']],  // Activate Gift Search switched off (1.117.0, blue season)
  ['GiftSearch.png', ['GiftSearch', 'GiftChoice']],  // same Refuse Gift button; GiftSearch comes first in the hub
  // 3 gifts picked, Select 3/3; its Selected E.G.O Gift header reads like the starting gift page's: GiftSearch comes first
  ['GiftSearchSelected.png', ['GiftSearch', 'GiftChoice', 'StartingGift']],
  ['GiftSearchConfirm.png', ['GiftSearch', 'GiftChoice']],  // "Consume 70 Starlight ...": GiftSearch confirms it
  ['GiftSearchGet.png', ['GiftGet', 'GiftSearch']],  // GiftGet comes first in the hub
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
  ['BattleTurnEven.png', ['BattleTurn']], // 8 slots (slot 4 a unit's second slot), Win Rate at x 1022
  ['BattleTurnStagger.png', ['BattleTurn']], // 6 of 7 slots staggered, Win Rate on, the START disc dim (#69)
  ['BattleTurnFocused.png', ['BattleTurn']], // focused encounter (#127): hollow left gear, one sinner in 7 slots, nothing picked
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
  ['ClaimBonusDialog.png', ['ExplorationReward', 'ExplorationComplete']],  // toggles ON: "Spend your 「Weekly Bonuses」..."
  // After that Confirm (live 2026-10-16): two popups over the summary, each closed by its Confirm.
  ['RewardsAcquired.png', ['ClaimPopup', 'PopupButton', 'ExplorationComplete']],
  ['PassLevelUp.png', ['ClaimPopup', 'PopupButton', 'ExplorationComplete']],
  // Rewards and events. The dialogs sit over their page, which still reads.
  ['RewardCard.png', ['RewardCard']],
  ['RewardCardForgo.png', ['RewardCardForgo', 'RewardCard']],
  ['GiftChoice.png', ['GiftChoice']],
  ['BossGiftTrials.png', ['GiftChoice']],
  ['BossGiftTrialsHard.png', ['GiftChoice']],
  ['GiftRefuseDialog.png', ['GiftRefuseDialog', 'GiftChoice']],
  ['EventStory.png', ['Event']],
  ['EventChoices.png', ['Event']],
  ['EventChoicesUsed.png', ['Event']],  // floor 5 boss's second round of questions: the first answer greyed out (#34)
  ['EventCheck.png', ['Event']],
  ['EventResult.png', ['Event']],
  // Shop: Leave stays readable under the shop's own dialogs and pages; the heal page has Return instead.
  ['Shop.png', ['Shop']],
  ['SuperShop.png', ['Shop']],
  ['ShopPurchase.png', ['Shop']],
  ['ShopFuse.png', ['Shop']],
  // #103 (live 2026-10-17, 1080p capture scaled to 720p): a fixed recipe's Fusion Available section over the owned gifts
  ['ShopFuseRecipe.png', ['Shop', 'ShopFusionAvailable']],
  ['ShopHeal.png', []],
]

// CI shards by node: SHARD=i SHARDS=n keeps every n-th node, and every image still runs its shard's nodes,
// so a node not in an image's hits still must miss. Unset runs everything.
const shard = Number(process.env.SHARD ?? 0)
const shards = Number(process.env.SHARDS ?? 1)
const nodes = [...new Set(screens.flatMap(([, hits]) => hits))].sort()
const mine = new Set(nodes.filter((_, i) => i % shards === shard))

const config: FullConfig = {
  cwd: import.meta.dirname,
  maaVersion: '5.14.3',
  maaLogDir: 'debug',
  interfacePath: 'assets/interface.json',
  check: {},
  test: {
    // maa-tools defaults to cpus/4 workers: 1 on a 4-core CI runner, where the test ran ~10 min serially.
    job: availableParallelism(),
    cases: [
      {
        configs: { controller: 'MuMu', resource: 'base', imageRoot: 'tests/screens' },
        cases: screens.map(([image, hits]) => ({ image, hits: hits.filter((n) => mine.has(n)) })),
      },
    ],
  },
}

export default config
