import { availableParallelism } from 'node:os'
import type { FullConfig } from '@nekosu/maa-tools'

// Every image runs every node named below, except the node marks: the map images only (below). A node not in its
// hits must miss (07-assets-and-testing.md).
const screens: [image: string, hits: string[]][] = [
  ['Title.png', ['GoToMirrorEntry', 'NavTitle']],
  ['TitleConnecting.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['TitleFading.png', ['Connecting', 'GoToMirrorEntry', 'NavTitle']],
  ['Loading.png', ['Loading']],
  ['MaintenanceNotice.png', ['MaintenanceNotice', 'PopupButton', 'GoToMirrorEntry', 'NavTitle']],  // live 2026-10-15, over the title
  // Synthetic (#83): EventStory with the notice's message line pasted into its text box. Only the
  // notice window stops the task, not the word in other text.
  ['EventMaintenanceText.png', ['Event']],
  // Live 2026-10-22 (#86, 1080p scaled to 720p) over the title, which reads through: the download dialog
  // (`Downloading 539.76 MB of data`, Close / Confirm) is Confirmed; the client too old for the server
  // (`Game client is not up to date`, Close / Go to Store) stops the bot, no button pressed.
  ['TitleDownload.png', ['DownloadDialog', 'GoToMirrorEntry', 'NavTitle']],
  ['TitleClientOutdated.png', ['ClientOutdated', 'GoToMirrorEntry', 'NavTitle']],
  // Synthetic (#86): the one-button notice window (live) as a one-button error box on the title; its one button.
  ['TitleErrorConfirm.png', ['PopupButton', 'GoToMirrorEntry', 'NavTitle']],
  // Synthetic, no capture: TitleErrorConfirm.png with the client's own mid-run update text (EN_MainUIText
  // remote_download_quit_game). DownloadDialog and PopupButton read it too; UpdateDialog comes first in the hub.
  ['UpdateDialog.synthetic.png', ['UpdateDialog', 'DownloadDialog', 'PopupButton', 'GoToMirrorEntry', 'NavTitle']],
  // Live 2026-10-21 (a new account): the title's User Agreement, unticked and both boxes ticked; the title reads through.
  ['UserAgreement.png', ['UserAgreement', 'GoToMirrorEntry', 'NavTitle']],
  ['UserAgreementTicked.png', ['UserAgreement', 'GoToMirrorEntry', 'NavTitle']],
  // Live 2026-10-21: the 17.77 GB download after the title's dialog, its two stages.
  ['DownloadingUpdate.png', ['Downloading']],
  ['DownloadingResources.png', ['Downloading']],
  // Synthetic (#84) over the title, live captures over the Mailbox below: the one-button notice window
  // (MaintenanceNotice's, live) relabelled as a server error with a countdown Retry or a Try Again button.
  // They put RetryPopup on every other screen.
  ['RetryCountdown.png', ['RetryPopup', 'GoToMirrorEntry', 'NavTitle']],
  ['TryAgain.png', ['RetryPopup', 'GoToMirrorEntry', 'NavTitle']],
  // Live 2026-10-20 (#84): the server error over the Mailbox after a request timed out, Close / Retry. Retry
  // counts down "Retry 5" to "Retry 1" with a dark frame first, then reads "Retry". The Mailbox under these
  // popups still reads: they come before it in the hub.
  ['ServerErrorRetryCountdown.png', ['RetryPopup', 'Mailbox', 'EnkephalinBar']],
  ['ServerErrorRetry.png', ['RetryPopup', 'Mailbox', 'EnkephalinBar']],
  // Live 2026-10-20 (#84): the network-unstable popup over the Mailbox with Wi-Fi off, Close only.
  ['NetworkUnstable.png', ['PopupButton', 'Mailbox', 'EnkephalinBar']],
  // The Parallel Superposition prompt after clearing floor 5 / 10 with the mode engaged (#85). Captured from the
  // game's own help sheet (the page behind it is the help text, not a map): the dialog is its live look, but where
  // it sits on screen is not confirmed. A Cancel / Confirm question, so PopupButton (one centred button) stays out.
  // Both are help pager pages, so HelpPager (ahead of HubText) closes them there.
  ['ParallelModePrompt.png', ['ParallelModePrompt', 'HelpPager']],
  ['ParallelModeExtreme.png', ['ParallelModePrompt', 'HelpPager']],
  // Live 2026-10-21 (#85, 1080p captures scaled to 720p): the main window's own popups and the help pager behind
  // every "i" button (Mirror Dungeon page 1 and its last page, Extract, Sinners). The tab bar dimmed under the
  // notices and the Mailbox misses NavMainTabs' 0.9; under the menu it still reads. The popups come first in the hub.
  // GoHome (#365): HomeReached is the Window tab lit, HomeWindowTab the same tab unlit (the bar shows with another tab
  // open, Drive and Sinners). The other tabs' lit look and a popup dimming the bar score at most 0.80 on them, so those
  // images (the notices, the Mailbox, the popups over them) must miss. The settings menu leaves the Window tab lit:
  // GoHome reads its popups before HomeReached.
  ['EventNotices.png', ['Notices', 'EnkephalinBar']],
  ['SystemNotices.png', ['Notices', 'EnkephalinBar']],
  ['Mailbox.png', ['Mailbox', 'EnkephalinBar']],
  ['SettingsMenu.png', ['SettingsMenu', 'GoToMirrorEntry', 'NavMainTabs', 'HomeReached', 'AssembleMain', 'EnkephalinBar']],
  ['HelpPager.png', ['HelpPager']],
  ['HelpPagerLast.png', ['HelpPager']],
  ['HelpPagerExtract.png', ['HelpPager']],
  ['HelpPagerSinners.png', ['HelpPager']],
  ['MainWindow.png', ['GoToMirrorEntry', 'NavMainTabs', 'HomeReached', 'AssembleMain', 'EnkephalinBar']],
  ['MainWindowFadeIn.png', ['GoToMirrorEntry', 'NavMainTabs', 'HomeReached', 'AssembleMain', 'EnkephalinBar']],
  ['MainWindowLater.png', ['GoToMirrorEntry', 'NavMainTabs', 'HomeReached', 'AssembleMain', 'EnkephalinBar']],  // live 2026-10-26: other numbers on the resource panel
  // Synthetic (#370): MainWindowLater.png with the bar's "22" painted down to "2": under a module's 20 Enkephalin.
  ['MainWindowLowEnkephalin.synthetic.png', ['GoToMirrorEntry', 'NavMainTabs', 'HomeReached', 'AssembleMain', 'EnkephalinBar']],
  // Live 2026-10-26: the Charge Enkephalin window over Drive, the tab bar dimmed under it: neither tab here. The
  // Enkephalin bar still reads under the dimming (#370), as on every screen that shows the resource panel.
  ['EnkephalinPanel.png', ['AssemblePanel', 'EnkephalinBar', 'AssembleAfter']],
  ['SinnersTab.png', ['GoToMirrorEntry', 'NavMainTabs', 'HomeWindowTab', 'EnkephalinBar']],
  ['Drive.png', ['GoToMirrorEntry', 'NavDrive', 'HomeWindowTab', 'EnkephalinBar']],
  ['EntryNewRun.png', ['MirrorEntryNewRun']],
  ['EntryPaused.png', ['MirrorEntryPaused']],
  // Synthetic (#94), no live capture yet: EntryNewRun.png with the Parallel Superposition label's OFF redrawn as ON.
  ['EntryParallelOn.png', ['ParallelModeOn', 'MirrorEntryNewRun']],
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
  // Live 2026-10-21 (#213): after an abnormality fight, over the map. The map's buttons read through (MirrorMap), so
  // RouteMap's guard looks for GiftGet first (COVERS in actions.py).
  ['GiftGetOverMap.png', ['GiftGet', 'MirrorMap']],
  ['StartingGiftSearchOff.png', ['StartingGift']],  // Activate Gift Search switched off (1.117.0, blue season)
  ['GiftSearch.png', ['GiftSearch', 'GiftChoice']],  // same Refuse Gift button; GiftSearch comes first in the hub
  // 3 gifts picked, Select 3/3. Its Selected E.G.O Gift header reads like the starting gift page's, but only that page
  // has the Activate Gift Search switch: live 2026-10-19 (#166), the page fading in read as StartingGift before its
  // blue title could be read. GiftSearchFadeIn.png: a frame of that fade-in (recording), the panel still sliding in.
  ['GiftSearchSelected.png', ['GiftSearch', 'GiftChoice']],
  ['GiftSearchFadeIn.png', ['GiftSearch', 'GiftChoice']],
  ['GiftSearchConfirm.png', ['GiftSearch', 'GiftChoice']],  // "Consume 70 Starlight ...": GiftSearch confirms it
  ['GiftSearchGet.png', ['GiftGet', 'GiftSearch']],  // GiftGet comes first in the hub
  ['GiftSearchForgo.png', ['GiftSearchForgo', 'GiftSearch', 'GiftChoice']],
  ['ThemePack.png', ['ThemePack']],
  ['ThemePackNormal.png', ['ThemePack']],
  ['ThemePackRefresh0.png', ['ThemePack', 'PackRefreshSpent']],  // live 2026-10-23 (#319): Refresh 0/3, greyed
  ['ThemePackRefresh1.png', ['ThemePack']],  // the same floor, Refresh 1/3
  ['MirrorMap.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeEvent']],
  // Map marks: the default ROIs fit a map at rest; RouteMap moves them with the bus.
  ['MapEvent.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeEvent']],
  ['MapFocused.png', ['MirrorMap', 'MapBus', 'MapLinkMid', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedHex']],
  ['MapPanned.png', ['MirrorMap', 'MapBus', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedHex', 'MapNodeEvent']],
  ['MapRock.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedRound', 'MapNodeEvent']],
  ['MapCards.png', ['MirrorMap', 'MapBus', 'MapLinkUp', 'MapLinkMid', 'MapLinkDown', 'MapNodeCost', 'MapNodeGift', 'MapNodeFocusedRound', 'MapNodeEvent']],
  ['MapShop.png', ['MirrorMap', 'MapBus', 'MapLinkDown', 'MapNodeShop']],
  ['MapBoss.png', ['MirrorMap', 'MapBus', 'MapLinkMid', 'MapNodeCost', 'MapNodeGift', 'MapNodeBoss']],
  ['MapNodePanel.png', ['MapNodePanel', 'MapBusZoomed']],  // the panel zooms the camera in on the bus
  // Live 2026-10-20 (#194): the map after backing out of a node's formation, zoomed in ~1.8x on the bus.
  ['MapZoomed.png', ['MirrorMap', 'MapBusZoomed']],
  // Battle. The forfeit screens (settings panel, Quit exploring) are read inside RouteMap's forfeit,
  // not by the hub, and the map icons still show through them.
  ['Formation.png', ['Formation']],
  ['FormationDetails.png', ['Formation']],
  // "You haven't Deployed any Sinners." on light parchment (live, #157): PopupButton's parchment gate; Formation reads
  // through it
  ['FormationNoSinners.png', ['PopupButton', 'Formation']],
  ['BattleTurn.png', ['BattleTurn']],
  ['BattleTurnLit.png', ['BattleTurn']],
  ['BattleTurnSolo.png', ['BattleTurn']], // 1-sinner formation: one slot, Win Rate at x ~740
  ['BattleTurnEven.png', ['BattleTurn']], // 8 slots (slot 4 a unit's second slot), Win Rate at x 1022
  ['BattleTurnStagger.png', ['BattleTurn']], // 6 of 7 slots staggered, Win Rate on, the START disc dim (#69)
  ['BattleTurnFocused.png', ['BattleTurn']], // focused encounter (#127): hollow left gear, one sinner in 7 slots, nothing picked
  ['BattleTurnSwarm.png', ['BattleTurn']], // a swarm of enemies over the battlefield, one sinner in 6 slots (live 2026-10-21)
  ['BattleTurnSwarmNext.png', ['BattleTurn']], // the same turn 3 s later: the swarm moved, the HUD did not
  ['BattlePause.png', ['BattlePause']],
  // Live 2026-10-22 (#215): the pause menu behind the gear, over the planning screen (Settings / Resume / Retry Stage /
  // Give Up). BattleMenu clicks Resume; the second frame is the menu fading out after that click. The Win Rate label
  // reads through the menu, so BattleTurn hits too: BattleHUD tries BattleMenu first.
  ['BattleMenu.png', ['BattleMenu', 'BattleTurn']],
  ['BattleMenuClosing.png', ['BattleMenu', 'BattleTurn']],
  ['Victory.png', ['Victory']],
  ['WipeDialog.png', ['WipeDialog', 'AssembleAfter']],
  ['DungeonProgress.png', ['MirrorMap', 'ProgressPanel', 'RecoverToWindow']],
  // Live 2026-10-22 (#215): the back key on the map, NORMAL floor 2. Synthetic: the same panel over a dimmed event
  // result page (live the back key opens it there too, #118); the page's own Continue button still reads.
  ['DungeonProgressNormal.png', ['MirrorMap', 'MapBus', 'ProgressPanel', 'RecoverToWindow']],
  ['EventProgressPanel.synthetic.png', ['Event', 'ProgressPanel', 'RecoverToWindow']],
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
  // Live 2026-10-20 (#196): a drag lifts one card, lit orange; the list scrolled to its top, bottom and back.
  ['EventChoicesLitTop.png', ['Event']],
  ['EventChoicesLitBottom.png', ['Event']],
  ['EventChoicesScrolledBack.png', ['Event']],
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

// The node marks (actions.MARKS) RouteMap reads around a slot next to the bus, only on the map: they run on the
// map screens alone (those MapBus hits), not on the other screens the bot never reads them on. #156: the
// FeatureMatch marks SIFT the whole image whatever their roi (measured in #163), ~1-3 s per image on a CI runner.
const marks = new Set(['MapNodeBoss', 'MapNodeFocusedHex', 'MapNodeFocusedRound', 'MapNodeCost', 'MapNodeGift',
  'MapNodeEvent', 'MapNodeShop'])
const mapScreens = screens.filter(([, hits]) => hits.includes('MapBus'))
const stray = screens.filter((s) => !mapScreens.includes(s) && s[1].some((n) => marks.has(n)))
if (stray.length) throw new Error(`node marks off the map: ${stray.map(([image]) => image)}`)

// CI shards by node: SHARD=i of SHARDS=n keeps one n-th of the nodes, and every image still runs its shard's
// nodes (a mark: every map image), so a node not in an image's hits still must miss. Unset runs everything.
// Shards are filled heaviest node first by its cost per image times the images it runs on; the cost is ms on a
// CI runner, from the MaaFW log of one unsharded run (2026-10-18); a node not listed counts 170. A stale cost
// only unbalances the shards: every node still runs in exactly one.
const cost: Record<string, number> = {
  MapNodeEvent: 2950, MapNodeShop: 1950, MaintenanceNotice: 1050, MapNodeFocusedHex: 1020, RetryPopup: 900,
  RecoverPauseConfirm: 790, DownloadDialog: 780, Victory: 730, LevelWarning: 570, ParallelModePrompt: 440,
  MirrorEnterDialog: 350, GiftRefuseDialog: 350, RewardCard: 340, RewardCardForgo: 340, MapNodeFocusedRound: 310,
  MapBus: 310, ClaimPopup: 290, GiftSearchForgo: 270, WipeDialog: 270, PopupButton: 250,
}
const shard = Number(process.env.SHARD ?? 0)
const shards = Number(process.env.SHARDS ?? 1)
const nodes = [...new Set(screens.flatMap(([, hits]) => hits))]
  .map((node) => ({ node, cost: (cost[node] ?? 170) * (marks.has(node) ? mapScreens : screens).length }))
  .sort((a, b) => b.cost - a.cost || a.node.localeCompare(b.node))
const load = Array<number>(shards).fill(0)
const mine = new Set<string>()
for (const { node, cost } of nodes) {
  const lightest = load.indexOf(Math.min(...load))
  load[lightest] += cost
  if (lightest === shard) mine.add(node)
}

const config: FullConfig = {
  cwd: import.meta.dirname,
  maaVersion: '5.14.3',
  maaLogDir: 'debug',
  interfacePath: 'assets/interface.json',
  check: {},
  test: {
    // maa-tools defaults to cpus/4 workers: 1 on a 4-core CI runner, where the test ran ~10 min serially. It forks one
    // process per worker (~0.5 GiB each), so capped at 4: all of a 4-core runner, ~2 GiB instead of ~6.6 GiB on a
    // 16-core PC.
    job: Math.min(4, availableParallelism()),
    cases: [
      {
        configs: { controller: 'MuMu', resource: 'base', imageRoot: 'tests/screens' },
        cases: screens.map(([image, hits]) => ({ image, hits: hits.filter((n) => mine.has(n) && !marks.has(n)) })),
      },
      {
        configs: { name: 'MuMu:base map marks', controller: 'MuMu', resource: 'base', imageRoot: 'tests/screens' },
        cases: mapScreens.map(([image, hits]) => ({ image, hits: hits.filter((n) => mine.has(n) && marks.has(n)) })),
      },
    ],
  },
}

export default config
