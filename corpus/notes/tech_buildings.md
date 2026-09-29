# 科技建筑的效果

`codex/buildings.md` 里「科技与中立」一节的效果文字来自本文件。**一行一条，`ID 正文`。**

效果是引擎行为——`rulesmd.ini` 里只有旗标（`Capturable=yes`、`SecretLab=yes` 之类），没有语义。故本文件是**人工确认过**的描述：数字来自 INI 与语料，行为由人核对。出处写在每条末尾，指 `corpus/raw/fandom/pages.jsonl` 里的页标题。

CAMACH 占领后自动维修范围内的地面载具、舰船与飞机；机器商店越多修得越快（约每几十秒回复 5% 结构值），且与精英级或单位自带的自行维修叠加。出处：`Tech machine shop`

CAOUTP 相当于带炮塔的维修站——炮塔类似盟军多功能步兵车，能打步兵与轻载具、也能对空；血量 2000，比双方标准维修厂（1200）耐打；占领后还能像建造厂一样扩展周围的可建造范围。出处：`Tech outpost`

CATHOSP 占领后全场步兵持续回血，不必进城。出处：`Tech hospital (Red Alert 2)`

CAAIRP 占领后获得伞兵技能，与美国的国家特色伞兵可共存；一次投下盟军 6 名 GI、苏联 9 名 Conscript、尤里 6 名 Initiate。出处：`Tech airport (Red Alert 2)`

CAOILD 占领当即得 1000，之后持续进账，约每周期 20。出处：`Tech oil derrick (Red Alert 2)`

CASLAB 解锁一个随机的、某国家专属的单位或建筑的建造权限，也可能给出已经能造的东西；某些任务里是预先指定的。经典作战模式下用处有限。出处：`Tech secret lab`

CAPOWR 提供 200 电力（与盟军电厂相同，高于苏联与尤里的 150），血量 800；免疫间谍破坏，也不会被飞碟吸电。出处：`Tech Civilian Power Plant`
