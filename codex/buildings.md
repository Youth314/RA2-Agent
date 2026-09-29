# 建筑

由 `corpus/raw/rulesmd.ini` 生成，共 398 个，不要手改。其中可建造 53、科技与中立 7、可进驻 164。

## 科技与中立

占了有用的那些。效果由人写（`corpus/notes/tech_buildings.md`）。

- **CAMACH** Tech Machine Shop — 占领后自动维修范围内的地面载具、舰船与飞机；机器商店越多修得越快（约每几十秒回复 5% 结构值），且与精英级或单位自带的自行维修叠加。出处：`Tech machine shop`
- **CAOUTP** Tech Outpost — 相当于带炮塔的维修站——炮塔类似盟军多功能步兵车，能打步兵与轻载具、也能对空；血量 2000，比双方标准维修厂（1200）耐打；占领后还能像建造厂一样扩展周围的可建造范围。出处：`Tech outpost`
- **CATHOSP** Tech Hospital — 占领后全场步兵持续回血，不必进城。出处：`Tech hospital (Red Alert 2)`
- **CAAIRP** Tech Airport — 占领后获得伞兵技能，与美国的国家特色伞兵可共存；一次投下盟军 6 名 GI、苏联 9 名 Conscript、尤里 6 名 Initiate。出处：`Tech airport (Red Alert 2)`
- **CAOILD** Tech Oil Derrick — 占领当即得 1000，之后持续进账，约每周期 20。出处：`Tech oil derrick (Red Alert 2)`
- **CASLAB** Tech Secret Lab — 解锁一个随机的、某国家专属的单位或建筑的建造权限，也可能给出已经能造的东西；某些任务里是预先指定的。经典作战模式下用处有限。出处：`Tech secret lab`
- **CAPOWR** Tech Civilian Power Plant — 提供 200 电力（与盟军电厂相同，高于苏联与尤里的 150），血量 800；免疫间谍破坏，也不会被飞碟吸电。出处：`Tech Civilian Power Plant`

也能占领，但只是地图装饰：
CAHOSP(Old Civilian Hospital) CAEAST01(Easter Island Statue)

## 可建造

- **GAPOWR** Allied Power Plant（盟军发电厂） · 造价 800 · 血 750 · wood · 电力 +200 · 前提 GACNST · 等级 1
- **GAREFN** Allied Ore Refinery（盟军矿厂） · 造价 2000 · 血 1000 · wood · 电力 -50 · 前提 POWER,GACNST · 等级 1 · refinery naval_dock
- **GAPILE** Allied Barracks（盟军兵营） · 造价 500 · 血 500 · steel · 电力 -10 · 前提 POWER,GACNST · 等级 2
- **GADEPT** Allied Service Depot（盟军维修厂） · 造价 800 · 血 1200 · wood · 电力 -25 · 前提 GAWEAP,GACNST · 等级 6 · repairs_units
- **GATECH** Allied Battle Lab（盟军实验室） · 造价 2000 · 血 500 · wood · 电力 -100 · 前提 GAWEAP,RADAR,GACNST · 等级 8
- **GAWEAP** Allied War Factory（盟军兵工厂） · 造价 2000 · 血 1000 · wood · 电力 -25 · 前提 PROC,GAPILE,GACNST · 等级 2
- **NAPOWR** Soviet Tesla Reactor（磁能反应炉） · 造价 600 · 血 750 · wood · 电力 +150 · 前提 NACNST · 等级 1
- **NATECH** Soviet Battle Lab（苏军实验室） · 造价 2000 · 血 500 · wood · 电力 -100 · 前提 NAWEAP,RADAR,NACNST · 等级 7
- **NAHAND** Soviet Barracks（苏军兵营） · 造价 500 · 血 500 · steel · 电力 -10 · 前提 POWER,NACNST · 等级 2
- **GAWALL** Allied Wall（盟军围墙） · 造价 100 · 血 300 · concrete · 前提 GAPILE · 等级 1
- **NARADR** Soviet Radar Tower（苏军雷达） · 造价 1000 · 血 1000 · wood · 电力 -50 · 前提 NAREFN,NACNST · 等级 3
- **NAWEAP** Soviet War Factory（苏军兵工厂） · 造价 2000 · 血 1000 · wood · 电力 -25 · 前提 PROC,NAHAND,NACNST · 等级 2
- **NAREFN** Soviet Ore Refinery（苏军矿厂） · 造价 2000 · 血 1000 · wood · 电力 -50 · 前提 POWER,NACNST · 等级 1 · refinery naval_dock
- **NAWALL** Soviet Wall（苏军围墙） · 造价 100 · 血 300 · concrete · 前提 NAHAND · 等级 1
- **NAPSIS** Yuri Psychic Sensor（心灵感应器） · 造价 1000 · 血 750 · wood · 电力 -50 · 前提 YACNST,PROC · 等级 3
- **NALASR** Soviet Sentry Gun（哨戒炮） · 造价 500 · 血 400 · steel · 前提 BARRACKS,NACNST · 等级 1 · Vulcan(50伤/26帧/射程0 弹头SA) · 每发 → none,special_1,special_2=50 flak,plate=40 light,steel=25 medium,heavy,concrete=12.5 wood=37.5
- **NASAM** Allied Patriot Missile（爱国者飞弹） · 造价 1000 · 血 900 · steel · 电力 -50 · 前提 BARRACKS,GACNST · 等级 4 · RedEye2(75伤/55帧/射程12 弹头SAMWH) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=75 wood,steel,concrete=0
- **GAYARD** Allied Shipyard（盟军船厂） · 造价 1000 · 血 1500 · concrete · 电力 -25 · 前提 PROC,POWER,GACNST · 等级 4 · repairs_units naval_dock
- **NAIRON** Soviet Iron Curtain Device（铁幕） · 造价 2500 · 血 750 · concrete · 电力 -200 · 前提 NATECH,NACNST · 等级 10
- **NADEPT** Soviet Service Depot（苏军维修厂） · 造价 800 · 血 1200 · wood · 电力 -20 · 前提 NAWEAP,NACNST · 等级 6 · repairs_units naval_dock
- **GACSPH** Allied Chrono Sphere（超时空传送仪） · 造价 2500 · 血 750 · concrete · 电力 -200 · 前提 GATECH,GACNST · 等级 10
- **GAWEAT** Allied Weather Controller（天气控制器） · 造价 5000 · 血 1000 · concrete · 电力 -200 · 前提 GATECH,GACNST · 等级 10
- **TESLA** Soviet Tesla Coil（磁暴线圈） · 造价 1500 · 血 600 · steel · 电力 -75 · 前提 POWER,RADAR,NACNST · 等级 5 · CoilBolt(200伤/80帧/射程7 弹头Electric) · 每发 → none,flak,plate,medium,heavy,special_2=200 light=170 wood,steel,concrete=100 special_1=400
- **NAMISL** Soviet Nuclear Missile Silo（核弹发射井） · 造价 5000 · 血 1000 · concrete · 电力 -200 · 前提 NATECH,NACNST · 等级 10
- **ATESLA** Allied Prism Cannon（光棱塔） · 造价 1500 · 血 600 · steel · 电力 -75 · 前提 POWER,RADAR,GACNST · 等级 6 · PrismShot(120伤/45帧/射程8 弹头PrismWarhead) · 每发 → none,special_1=240 flak,plate,light,medium,heavy,special_2=120 wood,steel,concrete=60
- **NAYARD** Soviet Shipyard（苏军造船厂） · 造价 1000 · 血 1500 · concrete · 电力 -20 · 前提 PROC,POWER,NACNST · 等级 2 · repairs_units naval_dock
- **GASPYSAT** Allied SpySat Uplink（间谍卫星） · 造价 1500 · 血 1000 · wood · 电力 -100 · 前提 GATECH,GACNST · 等级 9 · spy_satellite
- **GAGAP** Allied Gap Generator（裂缝产生器） · 造价 1000 · 血 600 · wood · 电力 -100 · 前提 GATECH,GACNST · 等级 7 · extra_power
- **GTGCAN** Allied Grand Cannon（法国巨炮GrandCannonWeapon） · 造价 2000 · 血 900 · steel · 电力 -100 · 前提 RADAR,GACNST · 等级 7 · GrandCannonWeapon(150伤/120帧/射程15 弹头GrandCannonWH) · 每发 → none,flak,plate,light,medium,heavy,steel,special_1,special_2=150 wood,concrete=75
- **NANRCT** Soviet Nuclear Reactor（核子反应堆） · 造价 1000 · 血 1000 · concrete · 电力 +2000 · 前提 NATECH,NACNST · 等级 9
- **GAPILL** Allied Pill Box（机枪碉堡） · 造价 500 · 血 400 · steel · 前提 BARRACKS,GACNST · 等级 1 · Vulcan2(50伤/26帧/射程0 弹头SA) · 每发 → none,special_1,special_2=50 flak,plate=40 light,steel=25 medium,heavy,concrete=12.5 wood=37.5
- **NAFLAK** Soviet Flak Cannon（防空炮） · 造价 1000 · 血 900 · steel · 电力 -50 · 前提 BARRACKS,NACNST · 等级 4 · FlakWeapon(40伤/20帧/射程12 弹头FlakWH) · 每发 → none=60 flak=32 plate=20 light,medium,special_1,special_2=40 heavy=8 wood,steel,concrete=0
- **NACLON** Yuri Cloning Vats（复制中心） · 造价 2500 · 血 1000 · wood · 电力 -200 · 前提 YATECH,YACNST · 等级 9
- **GAOREP** Allied Ore Processor（矿石精鍊器） · 造价 2500 · 血 900 · wood · 电力 -200 · 前提 GATECH,PROC,GACNST · 等级 10
- **GAAIRC** Allied Airforce Command Headquarters（盟军空军指挥部） · 造价 1000 · 血 600 · steel · 电力 -50 · 前提 GAREFN,GACNST · 等级 3 · naval_dock
- **AMRADR** Allied American Airforce Command Headquarters（美国空军指挥部） · 造价 1000 · 血 600 · steel · 电力 -50 · 前提 GAREFN,GACNST · 等级 3 · naval_dock
- **YAPOWR** Yuri Bio Reactor（生化反应炉） · 造价 600 · 血 700 · wood · 电力 +150 · 前提 YACNST · 等级 1 · extra_power
- **YABRCK** Yuri Barracks（尤里兵营） · 造价 500 · 血 500 · steel · 电力 -10 · 前提 POWER,YACNST · 等级 2
- **YAWEAP** Yuri War Factory（尤里兵工厂） · 造价 2000 · 血 1000 · wood · 电力 -25 · 前提 PROC,YABRCK,YACNST · 等级 2
- **YAYARD** Yuri Submarine Pen（尤里船厂） · 造价 1000 · 血 1500 · concrete · 电力 -25 · 前提 YACNST,POWER,PROC · 等级 4 · repairs_units naval_dock
- **YADEPT** ZZZ Yuri Service Depot · 造价 800 · 血 1200 · wood · 电力 -25 · 前提 YAWEAP,YACNST · 等级 15 · repairs_units
- **YATECH** Yuri Battle Lab（尤里实验室） · 造价 2000 · 血 500 · wood · 电力 -100 · 前提 YAWEAP,YACNST,RADAR · 等级 8
- **GAFWLL** Yuri Citadel Wall（尤里围墙） · 造价 100 · 血 300 · concrete · 前提 YABRCK · 等级 2
- **YAGGUN** Yuri Gattling Cannon（盖特机炮） · 造价 1000 · 血 810 · steel · 电力 -50 · 前提 BARRACKS,YACNST · 等级 4
- **YAPSYT** Yuri Psychic Tower（心灵控制塔） · 造价 1500 · 血 455 · steel · 电力 -100 · 前提 NAPSIS,YACNST · 等级 7 · MultipleMindControlTower(3伤/100帧/射程7 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=3 wood,steel,concrete=0
- **NAINDP** Soviet Industrial Plant（工业工厂） · 造价 2500 · 血 1000 · wood · 电力 -200 · 前提 NATECH,PROC,NACNST · 等级 10
- **YAGRND** Yuri Grinder（部队回收厂） · 造价 600 · 血 900 · wood · 电力 -50 · 前提 YAWEAP,YACNST · 等级 9
- **YAGNTC** Yuri Genetic Mutator Device（基因突变器） · 造价 2500 · 血 1000 · concrete · 电力 -200 · 前提 YATECH,YACNST · 等级 10
- **YAPPET** Yuri Puppet Master（心灵控制增幅器） · 造价 5000 · 血 1000 · concrete · 电力 -200 · 前提 YATECH,YACNST · 等级 10
- **NATBNK** Yuri Tank Bunker（坦克碉堡） · 造价 400 · 血 1000 · steel · 前提 YACNST · 等级 3 · naval_dock
- **GAROBO** Allied Robot Control Center（控制中心） · 造价 600 · 血 600 · wood · 电力 -100 · 前提 GAWEAP,GACNST · 等级 10
- **YAREFN** Yuri Ore Refinery（奴隶矿厂） · 造价 1750 · 血 2000 · medium · 前提 POWER,YACNST · 等级 1 · harvester cannot_sell · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **NABNKR** Soviet Battle Bunker（战斗碉堡） · 造价 500 · 血 600 · steel · 前提 NACNST · 等级 1

## 可进驻

拿来当掩体的。只给大小与驻军上限。

| 建筑 | 名字 | 地基 | 驻军上限 | 装甲 | 血 |
|---|---|---|---|---|---|
| CACHIG01 | Chigo Brick Building | — | 10 | steel | 1000 |
| CACHIG02 | Chigo Brick Building var2 | — | 10 | steel | 1000 |
| CACHIG03 | Chigo Office Building | — | 10 | steel | 1000 |
| CACHIG04 | Chicago Associates Center | — | 10 | concrete | 1000 |
| CACHIG05 | Chicago Sears Tower | — | 10 | concrete | 1000 |
| CACITY01 | ZZZ Building | — | 10 | steel | 1000 |
| CACITY02 | ZZZ Building | — | 10 | steel | 1000 |
| CACITY03 | ZZZ Building | — | 10 | steel | 1000 |
| CACITY04 | ZZZ Building | — | 10 | steel | 1000 |
| CAEGYP02 | Egypt Small Pyramid | — | 10 | wood | 1000 |
| CAEUR04 | Euro Building 04 | — | 10 | steel | 400 |
| CAFRMA | Farmhouse | — | 10 | wood | 400 |
| CAGAS01 | Gas Station | — | 10 | wood | 1000 |
| CAIND01 | Industrial building | — | 10 | steel | 1000 |
| CALA01 | LA Keegan Produce | — | 10 | wood | 1000 |
| CALA04 | LA Hollywood Bowl | — | 10 | wood | 1000 |
| CALA05 | LA LAX | — | 10 | wood | 1000 |
| CALA06 | LA Control Tower | — | 10 | wood | 1000 |
| CALA07 | LA Movie Theater | — | 10 | wood | 1000 |
| CALA08 | LA Car Dealership | — | 10 | concrete | 1000 |
| CALA09 | LA Circle S | — | 10 | wood | 1000 |
| CALA14 | LA Mini Mall 02 | — | 10 | concrete | 1000 |
| CALA15 | LA Mini Mall 03 | — | 10 | concrete | 1000 |
| CALAB | Einstein's Lab | — | 10 | steel | 1000 |
| CALOND01 | London Victorian Home 1 | — | 10 | wood | 1000 |
| CALOND03 | London Pub | — | 10 | wood | 1000 |
| CALOND04 | LONDON PARLAIMENT | — | 10 | wood | 1000 |
| CALOND05 | LONDON BIG BEN | — | 10 | wood | 1000 |
| CALOND06 | LONDON TOWER | — | 10 | wood | 1000 |
| CAMEX02 | Mayan Castillo | — | 10 | concrete | 1000 |
| CAMIAM01 | Miami Hotel 01 | — | 10 | steel | 1000 |
| CAMIAM02 | Miami Hotel 02 | — | 10 | steel | 1000 |
| CAMIAM03 | Miami Hotel 03 | — | 10 | steel | 1000 |
| CAMIAM05 | Miami Hotel 05 | — | 10 | steel | 1000 |
| CAMIAM06 | Miami Hotel 06 | — | 10 | steel | 1000 |
| CAMIAM07 | Miami Hotel 07 | — | 10 | steel | 1000 |
| CAMORR01 | Morocco Generic | — | 10 | wood | 1000 |
| CAMORR02 | Morocco Generic02 | — | 10 | wood | 1000 |
| CAMORR03 | Morroco Generic03 | — | 10 | wood | 1000 |
| CAMORR04 | Morroco Generic04 | — | 10 | wood | 1000 |
| CAMORR05 | Morroco Bar 01 | — | 10 | wood | 1000 |
| CAMORR06 | Morroco Bar 02 | — | 10 | wood | 1000 |
| CAMORR07 | Morroco Generic07 | — | 10 | wood | 1000 |
| CAMORR08 | Morroco Generic08 | — | 10 | wood | 1000 |
| CAMORR09 | Morroco Generic09 | — | 10 | wood | 1000 |
| CAMORR10 | Morroco Generic10 | — | 10 | wood | 1000 |
| CANEWY01 | Building | — | 10 | steel | 1000 |
| CANEWY05 | ZZZ World Trade Center | — | 10 | concrete | 1000 |
| CANEWY06 | Wall Street Office | — | 10 | steel | 1000 |
| CANEWY07 | Wall Street Office Var 2 | — | 10 | steel | 1000 |
| CANEWY08 | Wall Street Office Var 3 | — | 10 | steel | 1000 |
| CANEWY10 | NY Building 10 | — | 10 | steel | 1000 |
| CANEWY11 | NY Building 11 | — | 10 | steel | 1000 |
| CANEWY12 | NY Building 12 | — | 10 | steel | 1000 |
| CANEWY13 | NY Building 13 | — | 10 | steel | 1000 |
| CANEWY14 | NY Building 14 | — | 10 | steel | 1000 |
| CANEWY15 | NY Building 15 | — | 10 | steel | 1000 |
| CANEWY16 | NY Building 16 | — | 10 | steel | 1000 |
| CANEWY17 | NY Building 17 | — | 10 | steel | 1000 |
| CANEWY18 | NY Building 18 | — | 10 | steel | 1000 |
| CANEWY20 | Warehouse | — | 10 | steel | 1000 |
| CANEWY21 | Warehouse B | — | 10 | steel | 1000 |
| CANWY05 | NY Building 05 | — | 10 | steel | 1000 |
| CANWY09 | NY Building 09 | — | 10 | steel | 400 |
| CANWY22 | NY Building 22 | — | 10 | steel | 400 |
| CANWY23 | NY Building 23 | — | 10 | steel | 400 |
| CANWY24 | NY Building 24 | — | 10 | steel | 400 |
| CANWY25 | NY Building 25 | — | 10 | steel | 400 |
| CANWY26 | NY Building 26 | — | 10 | steel | 400 |
| CAPARS02 | Large Paris Building Var 1 | — | 10 | steel | 1000 |
| CAPARS08 | Large Paris Building Var 2 | — | 10 | steel | 1000 |
| CAPARS09 | Large Paris Building Var 3 | — | 10 | steel | 1000 |
| CAPARS10 | Paris Bistro Var 1 | — | 10 | wood | 1000 |
| CAPARS12 | Paris Notre Dame | — | 10 | concrete | 1000 |
| CAPARS13 | Paris Bistro Var 2 | — | 10 | concrete | 1000 |
| CAPARS14 | Paris Bistro Var 3 | — | 10 | concrete | 1000 |
| CAPRS03 | Paris Louvre | — | 10 | concrete | 500 |
| CARUS01 | Russian Basil's Cathedral | — | 10 | concrete | 1000 |
| CARUS02G | Russain Kremlin Wall Clock Tower | — | 10 | concrete | 1000 |
| CARUS03 | Russain Kremlin Palace | — | 10 | concrete | 1000 |
| CARUS07 | Russain Red Square Circle Thing | — | 10 | concrete | 1000 |
| CASANF01 | San Fran Victorian Home 1 | — | 10 | wood | 1000 |
| CASANF02 | San Fran Victorian Home 2 | — | 10 | wood | 1000 |
| CASANF03 | San Fran Victorian Home 3 | — | 10 | wood | 1000 |
| CASANF05 | San Fran Alcatraz | — | 10 | wood | 1000 |
| CASANF06 | San Fran Victorian Home 4 | — | 10 | wood | 1000 |
| CASANF07 | San Fran Victorian Home 5 | — | 10 | wood | 1000 |
| CASANF08 | San Fran Victorian Home 6 | — | 10 | wood | 1000 |
| CASANF17 | San Fran Misc Bldg 1 | — | 10 | wood | 1000 |
| CASANF18 | San Fran Misc Bldg 2 | — | 10 | wood | 1000 |
| CASEAT01 | Seattle Space Needle | — | 10 | wood | 1000 |
| CASEAT02 | MicroSpam Campus | — | 10 | wood | 1000 |
| CASTL01 | St Louis Building A | — | 10 | steel | 1000 |
| CASTL02 | St Louis Building B | — | 10 | steel | 1000 |
| CASTL03 | St Louis Building C | — | 10 | steel | 1000 |
| CASTL04 | St Louis Arch | — | 10 | steel | 1000 |
| CASWST01 | Southwest Building | — | 10 | steel | 1000 |
| CASYDN02 | Sydney Kangaroo Burger | — | 10 | wood | 1000 |
| CASYDN03 | Sydney Opera House | — | 10 | wood | 1000 |
| CATECH01 | Communications | — | 10 | steel | 400 |
| CATEXS01 | Texs01 Building | — | 10 | steel | 1000 |
| CATEXS02 | Alamo | — | 10 | concrete | 2000 |
| CATEXS03 | San Antonio Office building | — | 10 | steel | 1000 |
| CATEXS04 | San Antonio Office building Var 2 | — | 10 | steel | 1000 |
| CATEXS05 | San Antonio Office building Var 3 | — | 10 | steel | 1000 |
| CATEXS06 | Texas Office Building | — | 10 | steel | 1000 |
| CATEXS07 | Texas Office Building var2 | — | 10 | steel | 1000 |
| CATEXS08 | Texas Office Building var3 | — | 10 | steel | 1000 |
| CATRAN01 | Transylvania Crypt 1 | — | 10 | concrete | 1000 |
| CATRAN02 | Transylvania Crypt 2 | — | 10 | concrete | 1000 |
| CAWA2A | Wash Pent A | — | 10 | concrete | 600 |
| CAWA2B | Wash Pent B | — | 10 | concrete | 600 |
| CAWA2C | Wash Pent C | — | 10 | concrete | 600 |
| CAWA2D | Wash Pent D | — | 10 | concrete | 600 |
| CAWASH03 | Wash Building 3 | — | 10 | steel | 1000 |
| CAWASH04 | Wash Building 4 | — | 10 | steel | 1000 |
| CAWASH05 | Wash Building 5 | — | 10 | steel | 1000 |
| CAWASH06 | Wash Building 6 | — | 10 | steel | 1000 |
| CAWASH07 | Wash Building 7 | — | 10 | steel | 1000 |
| CAWASH08 | Wash Building 8 | — | 10 | steel | 1000 |
| CAWASH09 | Wash Building 9 | — | 10 | steel | 1000 |
| CAWASH10 | Wash Building 10 | — | 10 | steel | 1000 |
| CAWASH11 | Wash Building 11 | — | 10 | steel | 1000 |
| CAWASH13 | Wash Building 13 | — | 10 | steel | 1000 |
| CAWASH17 | Smithsonian Natural History Museum | — | 10 | concrete | 1000 |
| YAPPPT | Partially Built Psychic Dominator | — | 10 | wood | 1000 |
| CAARMY01 | Army Tent | — | 8 | wood | 200 |
| CABUNK01 | Concrete Bunker 01 | — | 8 | steel | 2000 |
| CABUNK02 | Concrete Bunker 02 | — | 8 | steel | 2000 |
| CABUNK03 | Concrete Bunker 03 | — | 8 | steel | 2000 |
| CABUNK04 | Concrete Bunker 04 | — | 8 | steel | 2000 |
| CAMSC10 | McBurger Kong | — | 8 | wood | 1000 |
| CARUS04 | Moscow City A | — | 8 | steel | 1000 |
| CARUS05 | Moscow City B | — | 8 | steel | 1000 |
| CARUS06 | Moscow City C | — | 8 | steel | 1000 |
| CAFARM01 | Farm | — | 6 | wood | 400 |
| CAMSC07 | Thatched Hut Chief | — | 6 | concrete | 600 |
| CAMSC08 | Thatched Hut A | — | 6 | wood | 200 |
| CAMSC09 | Thatched Hut B | — | 6 | wood | 200 |
| CAPARS04 | Paris Building 4 | — | 6 | steel | 500 |
| CAPARS05 | Paris Building 5 | — | 6 | steel | 500 |
| CAPARS06 | Paris Building 6 | — | 6 | steel | 500 |
| CABARN02 | Farm Barn 02 | — | 5 | wood | 500 |
| CAFARM06 | Lighthouse | — | 5 | steel | 500 |
| CAHSE01 | American House 01 | — | 5 | wood | 600 |
| CAHSE02 | American House 02 | — | 5 | wood | 400 |
| CAHSE03 | American House 03 | — | 5 | wood | 400 |
| CAHSE04 | American House 04 | — | 5 | wood | 400 |
| CAHSE05 | American Mobile Home A | — | 5 | wood | 300 |
| CAHSE06 | American Mobile Home B | — | 5 | wood | 300 |
| CAHSE07 | American House 07 | — | 5 | wood | 600 |
| CAMOV02 | Drive In Movie Concession Stand | — | 5 | steel | 1000 |
| CARUS08 | Russain Gum Corner | — | 5 | steel | 1000 |
| CARUS09 | Russian Gum Middle | — | 5 | steel | 1000 |
| CARUS10 | Russian Gum Wall N_S | — | 5 | steel | 1000 |
| CARUS11 | Russian Gum Wall E_W | — | 5 | steel | 1000 |
| NABNKR | Soviet Battle Bunker | — | 5 | steel | 600 |
| CAARMY02 | Army Tent | — | 4 | wood | 200 |
| CAARMY03 | Army Tent | — | 4 | wood | 200 |
| CAARMY04 | Army Tent | — | 4 | wood | 200 |
| CAEUR1 | Euro Cottage A | — | 3 | wood | 300 |
| CAEUR2 | Euro Cottage B | — | 3 | wood | 300 |
| CAMIAM04 | Lifeguard Hut | — | 3 | wood | 200 |
| CAFRMB | Farm Outhouse | — | 1 | wood | 50 |
