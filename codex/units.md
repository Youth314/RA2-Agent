# 单位

由 `corpus/raw/rulesmd.ini` 生成，共 155 个：可建造 74，其它（民用、任务用）81。不要手改。

「每发 →」是主武器对每种装甲的每次开火伤害，同值的并成一档；装甲代号顺序同 `corpus/derived/rules.json` 的 `armor_types`。

## 可建造（74）

### 步兵（31）

- **E1** GI · 步兵 · 造价 200 · 血 125 · none · 速 4 · 视野 5 · 前提 GAPILE · 等级 1 · M60(15伤/20帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **E2** Conscript · 步兵 · 造价 100 · 血 125 · flak · 速 4 · 视野 5 · 前提 NAHAND · 等级 1 · M1Carbine(15伤/25帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **SHK** Shock Trooper · 步兵 · 造价 500 · 血 130 · Plate · 速 4 · 视野 6 · 前提 NAHAND · 等级 5 · ElectricBolt(50伤/60帧/射程3 弹头Shock) · 每发 → none,flak,plate,medium,heavy,special_2=50 light=42.5 wood,steel,concrete=25 special_1=100
- **ENGINEER** Engineer · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **JUMPJET** Rocketeer · 步兵 · 造价 600 · 血 125 · none · 速 9 · 视野 8 · 前提 GAPILE,RADAR · 等级 3 · 20mm(25伤/30帧/射程5 弹头SSA) · 每发 → none,flak,plate,special_1,special_2=25 light=15 medium,heavy=10 wood=18.75 steel=12.5 concrete=6.25
- **GHOST** SEAL · 步兵 · 造价 1000 · 血 125 · flak · 速 5 · 视野 8 · 前提 GAPILE,RADAR · 等级 9 · MP5(125伤/10帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **YURI** Yuri Clone · 步兵 · 造价 800 · 血 100 · none · 速 4 · 视野 12 · 前提 YABRCK,NAPSIS · 等级 10 · MindControl(1伤/200帧/射程7 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=1 wood,steel,concrete=0
- **IVAN** Crazy Ivan · 步兵 · 造价 600 · 血 125 · none · 速 4 · 视野 6 · 前提 NAHAND,NARADR · 等级 5 · IvanBomber(400伤/50帧/射程0 弹头IvanBomb) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=400
- **DESO** Desolater · 步兵 · 造价 600 · 血 150 · plate · 速 4 · 视野 6 · 前提 NAHAND,RADAR · 等级 8 · RadBeamWeapon(125伤/50帧/射程6 弹头RadBeamWarhead) · 每发 → none,flak,plate,special_1,special_2=125 light=25 medium=18.75 heavy=12.5 wood,steel,concrete=0
- **DOG** Attack Dog · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 Barracks · 等级 2 · BadTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **CLEG** Chrono Legionnaire · 步兵 · 造价 1500 · 血 125 · none · 速 5 · 视野 8 · 前提 GAPILE,TECH · 等级 10 · NeutronRifle(8伤/120帧/射程5 弹头ChronoBeam) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1=8 special_2=0
- **SPY** Spy · 步兵 · 造价 1000 · 血 100 · flak · 速 4 · 视野 9 · 前提 GAPILE,GATECH · 等级 5 · MakeupKit(1伤/100帧/射程-2 弹头Snapshot) · 每发 → none,flak,plate,special_1,special_2=1 light,medium,heavy,wood,steel,concrete=0
- **CCOMAND** Chrono Commando · 步兵 · 造价 2000 · 血 100 · none · 速 5 · 视野 8 · 前提 BARRACKS · 等级 9 · ChronoMP5(125伤/10帧/射程6 弹头HollowPointNoBuilding) · 每发 → none=250 flak,special_2=125 plate,special_1=93.75 light,medium,heavy=1.25 wood,steel,concrete=0
- **PTROOP** Psi-Corp Trooper · 步兵 · 造价 1000 · 血 100 · none · 速 5 · 视野 8 · 前提 BARRACKS · 等级 9 · MindControl(1伤/200帧/射程7 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=1 wood,steel,concrete=0
- **CIVAN** Chrono Ivan · 步兵 · 造价 1750 · 血 100 · none · 速 6 · 视野 8 · 前提 BARRACKS · 等级 9 · IvanBomber(400伤/50帧/射程0 弹头IvanBomb) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=400
- **YURIPR** Yuri Prime · 步兵 · 造价 1500 · 血 150 · flak · 速 6 · 视野 9 · 前提 YABRCK,YATECH · 等级 10 · SuperMindControl(1伤/200帧/射程7 弹头ControllerBuilding) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **SNIPE** Sniper · 步兵 · 造价 600 · 血 125 · none · 速 4 · 视野 8 · 前提 GAPILE,RADAR · 等级 1 · AWP(125伤/150帧/射程14 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **TANY** Tanya · 步兵 · 造价 1500 · 血 200 · flak · 速 6 · 视野 8 · 前提 GAPILE,GATECH · 等级 9 · DoublePistols(125伤/5帧/射程6 弹头HollowPoint2) · 每发 → none,flak,plate,special_2=125 light,medium,heavy=0 wood,steel,concrete,special_1=1.25
- **FLAKT** Flak Trooper · 步兵 · 造价 300 · 血 100 · none · 速 4 · 视野 5 · 前提 NAHAND,NARADR · 等级 1 · FlakGuyGun(20伤/20帧/射程5 弹头FlakTWH) · 每发 → none=30 flak=25 plate,special_1,special_2=20 light=12 medium,heavy,concrete=2 wood=6 steel=4
- **TERROR** Terrorist · 步兵 · 造价 200 · 血 75 · flak · 速 6 · 视野 9 · 前提 NAHAND,RADAR · 等级 5 · TerrorBomb(225伤/10帧/射程0 弹头TerrorBombWH) · 每发 → none,steel=337.5 flak,plate,wood,special_1,special_2=225 light=202.5 medium,heavy=112.5 concrete=67.5
- **SENGINEER** Soviet Engineer · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **ADOG** Allied Attack Dog · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 Barracks · 等级 2 · GoodTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **YENGINEER** Yuri Engineer · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **GGI** Guardian GI · 步兵 · 造价 400 · 血 100 · none · 速 3 · 视野 6 · 前提 GAPILE · 等级 2 · M60(15伤/20帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **INIT** Yuri Initiate · 步兵 · 造价 200 · 血 100 · none · 速 4 · 视野 9 · 前提 YABRCK · 等级 1 · PsychicJab(25伤/15帧/射程0 弹头SAFlame) · 每发 → none,special_1,special_2=25 flak,plate=20 light,steel=12.5 medium,heavy,concrete=6.25 wood=18.75
- **BORIS** Boris · 步兵 · 造价 1500 · 血 200 · flak · 速 5 · 视野 9 · 前提 NAHAND,NATECH · 等级 9 · AKM(65伤/20帧/射程7 弹头BORISWH) · 每发 → none,flak=130 plate,special_1,special_2=65 light,medium,heavy=32.5 wood,steel,concrete=0.65
- **BRUTE** Yuri Brute · 步兵 · 造价 500 · 血 200 · plate · 速 6 · 视野 8 · 前提 YABRCK · 等级 5 · Punch(100伤/60帧/射程0 弹头Battering) · 每发 → none,flak,plate,special_2=100 light,medium,heavy=0 wood,steel=30 concrete=20 special_1=200
- **VIRUS** Yuri Virus · 步兵 · 造价 700 · 血 100 · none · 速 4 · 视野 9 · 前提 YABRCK,RADAR · 等级 1 · Virusgun(125伤/100帧/射程10 弹头Virus) · 每发 → none,flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **LUNR** Lunar Infantry · 步兵 · 造价 600 · 血 125 · none · 速 9 · 视野 8 · 前提 NAPILE,RADAR · 等级 11 · Lunarlaser(25伤/20帧/射程7 弹头LUNARWH) · 每发 → none,flak,light,medium,heavy,special_1,special_2=25 plate=20 wood=7.5 steel,concrete=5
- **YDOG** Attack Dog (Yuri version) · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 NAHAND · 等级 2 · BadTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **YADOG** Allied Attack Dog (Yuri version) · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 GAPILE · 等级 2 · GoodTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0

### 载具（41）

- **AMCV** Allied Construction Vehicle · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 6 · 前提 GAWEAP,GADEPT · 等级 10
- **HARV** War Miner · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 前提 NAWEAP,PROC · 等级 1 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **APOC** Apocalypse · 载具 · 造价 1750 · 血 800 · heavy · 速 4 · 视野 6 · 前提 NAWEAP,NATECH · 等级 7 · 120mmx(100伤/80帧/射程0 弹头ApocAP) · 每发 → none,flak,plate=25 light=75 medium,heavy,wood,steel,special_2=100 concrete=70 special_1=60
- **HTNK** Rhino Heavy Tank · 载具 · 造价 900 · 血 400 · heavy · 速 6 · 视野 8 · 前提 NAWEAP · 等级 2 · 120mm(90伤/65帧/射程0 弹头AP) · 每发 → none,flak=22.5 plate=13.5 light=67.5 medium,heavy,special_2=90 wood=58.5 steel=40.5 concrete,special_1=54
- **SAPC** Armored Transport · 载具 · 造价 900 · 血 300 · heavy · 速 6 · 视野 6 · 前提 NAYARD · 等级 2 · 载员 12
- **MTNK** Grizzly Battle Tank · 载具 · 造价 700 · 血 300 · heavy · 速 7 · 视野 8 · 前提 GAWEAP · 等级 2 · 105mm(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39
- **CARRIER** Aircraft Carrier · 载具 · 造价 2000 · 血 800 · heavy · 速 4 · 视野 7 · 前提 GAYARD,TECH · 等级 7 · HornetLauncher(1伤/150帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **V3** V3 Launcher · 载具 · 造价 800 · 血 150 · light · 速 4 · 视野 7 · 前提 NAWEAP,NARADR · 等级 3 · V3Launcher(1伤/150帧/射程18 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **ZEP** Kirov Airship · 载具 · 造价 2000 · 血 2000 · medium · 速 5 · 视野 8 · 前提 NAWEAP,NATECH · 等级 10 · BlimpBomb(250伤/50帧/射程0 弹头BlimpHE) · 每发 → none,flak,plate,special_1,special_2=250 light=175 medium,heavy=87.5 wood=212.5 steel=187.5 concrete=125
- **DRON** Terror Drone · 载具 · 造价 500 · 血 100 · special_1 · 速 10 · 视野 4 · 前提 NAWEAP · 等级 4 · DroneJump(50伤/60帧/射程0 弹头Parasite) · 每发 → none,flak,plate,light,medium,heavy=50 wood,steel,concrete,special_1,special_2=0
- **HTK** Flak Track · 载具 · 造价 500 · 血 180 · heavy · 速 8 · 视野 8 · 前提 NAWEAP · 等级 3 · 载员 5 · FlakTrackGun(25伤/25帧/射程5 弹头FlakTWH) · 每发 → none=37.5 flak=31.25 plate,special_1,special_2=25 light=15 medium,heavy,concrete=2.5 wood=7.5 steel=5
- **DEST** Destroyer · 载具 · 造价 1000 · 血 600 · heavy · 速 6 · 视野 7 · 前提 GAYARD · 等级 4 · 155mm(60伤/110帧/射程8 弹头ARTYHE) · 每发 → none,light,wood,steel,special_1,special_2=60 flak=48 plate,medium,heavy,concrete=36
- **SUB** Typhoon Attack Sub · 载具 · 造价 1000 · 血 600 · heavy · 速 4 · 视野 4 · 前提 NAYARD · 等级 2 · SubTorpedo(100伤/120帧/射程7 弹头APSplash) · 每发 → none,flak,plate,special_1=25 light=75 medium,heavy,special_2=100 wood,steel=65 concrete=60
- **AEGIS** Aegis Cruiser · 载具 · 造价 1200 · 血 800 · light · 速 4 · 视野 8 · 前提 GAYARD,RADAR · 等级 7 · Medusa(100伤/15帧/射程12 弹头SAMWH) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=100 wood,steel,concrete=0
- **LCRF** Landing Craft · 载具 · 造价 900 · 血 300 · light · 速 6 · 视野 6 · 前提 GAYARD · 等级 4 · 载员 12
- **DRED** Dreadnought · 载具 · 造价 2000 · 血 800 · heavy · 速 4 · 视野 7 · 前提 NAYARD,NATECH · 等级 6 · DredLauncher(50伤/50帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=50
- **SHAD** BlackHawk Transport · 载具 · 造价 1000 · 血 175 · light · 速 14 · 视野 7 · 前提 GAWEAP · 等级 7 · 载员 5 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25
- **SQD** Giant Squid · 载具 · 造价 1000 · 血 200 · light · 速 8 · 视野 5 · 前提 NAYARD,NATECH · 等级 9 · SquidGrab(15伤/99帧/射程0 弹头ParasitePlus) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=15
- **DLPH** Dolphin · 载具 · 造价 500 · 血 200 · light · 速 8 · 视野 4 · 前提 GAYARD,GATECH · 等级 5 · SonicZap(4伤/120帧/射程6 弹头SonicWarhead) · 每发 → none,flak,plate,light,wood,special_1,special_2=4 medium,heavy=3.2 steel,concrete=2.4
- **SMCV** Soviet Construction Vehicle · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 6 · 前提 NAWEAP,NADEPT · 等级 10
- **TNKD** Tank Destroyer · 载具 · 造价 900 · 血 400 · heavy · 速 5 · 视野 8 · 前提 GAWEAP,RADAR · 等级 2 · SABOT(150伤/70帧/射程5 弹头UltraAP) · 每发 → none,flak,plate,wood,steel,concrete,special_1=3 light,heavy,special_2=150 medium=60
- **TTNK** Tesla Tank · 载具 · 造价 1200 · 血 300 · heavy · 速 6 · 视野 8 · 前提 NAWEAP,NARADR · 等级 10 · TankBolt(135伤/75帧/射程4 弹头Electric) · 每发 → none,flak,plate,medium,heavy,special_2=135 light=114.75 wood,steel,concrete=67.5 special_1=270
- **LTNK** Lasher Light Tank · 载具 · 造价 700 · 血 300 · heavy · 速 7 · 视野 8 · 前提 YAWEAP · 等级 2 · ATGUN(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39
- **CMIN** Chrono Miner · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 前提 GAWEAP,PROC · 等级 1
- **SREF** Prism Tank · 载具 · 造价 1200 · 血 150 · light · 速 4 · 视野 8 · 前提 GAWEAP,GATECH · 等级 8
- **HYD** Sea Scorpion · 载具 · 造价 600 · 血 400 · heavy · 速 8 · 视野 8 · 前提 NAYARD,NARADR · 等级 6 · FlakTrackGun(25伤/25帧/射程5 弹头FlakTWH) · 每发 → none=37.5 flak=31.25 plate,special_1,special_2=25 light=15 medium,heavy,concrete=2.5 wood=7.5 steel=5
- **MGTK** Mirage Tank · 载具 · 造价 1000 · 血 200 · light · 速 7 · 视野 9 · 前提 GAWEAP,GATECH · 等级 9
- **FV** IFV · 载具 · 造价 600 · 血 200 · light · 速 10 · 视野 8 · 前提 GAWEAP · 等级 3 · 载员 1 · HoverMissile(25伤/50帧/射程6 弹头HE) · 每发 → none,flak,plate,special_2=25 light,medium=17.5 heavy=8.75 wood=18.75 steel=10 concrete=5 special_1=20
- **DTRUCK** Demolitions Truck · 载具 · 造价 1500 · 血 150 · light · 速 5 · 视野 5 · 前提 NAWEAP,RADAR · 等级 10 · Demobomb(300伤/80帧/射程1 弹头DemobombWH) · 每发 → none,flak,plate,light,special_1,special_2=300 medium,heavy=150 wood=240 steel=450 concrete=30
- **YHVR** Hover Transport Yuri · 载具 · 造价 900 · 血 300 · heavy · 速 6 · 视野 6 · 前提 YAYARD · 等级 2 · 载员 12
- **PCV** Yuri Construction Vehicle · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 8 · 前提 YAWEAP,YAGRND · 等级 10
- **SMIN** Slave Miner · 载具 · 造价 1750 · 血 2000 · medium · 速 3 · 视野 4 · 前提 YAWEAP · 等级 1 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **YTNK** Gattling Tank · 载具 · 造价 600 · 血 210 · light · 速 6 · 视野 10 · 前提 YAWEAP · 等级 4 · AGGattling(25伤/16帧/射程6 弹头GattWH) · 每发 → none=25 flak=20 plate=17.5 light,special_2=12.5 medium=7.5 heavy,wood=2.5 steel=1.25 concrete=0.75 special_1=50
- **BFRT** Battle Fortress · 载具 · 造价 2000 · 血 600 · heavy · 速 4 · 视野 6 · 前提 GAWEAP,GATECH · 等级 10 · 载员 5 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **TELE** Magnetron · 载具 · 造价 1000 · 血 150 · light · 速 5 · 视野 10 · 前提 YAWEAP,NAPSIS · 等级 2 · MagneticBeam(5000伤/20帧/射程12 弹头LocomotorBeam) · 每发 → none,flak,plate,wood,steel,concrete,special_2=0 light,medium,heavy,special_1=5000
- **CAOS** Chaos Drone · 载具 · 造价 1000 · 血 130 · light · 速 8 · 视野 6 · 前提 YAWEAP · 等级 4 · ChaosAttack(600伤/45帧/射程3 弹头PsychGasCreate) · 每发 → none,flak,plate,special_1,special_2=600 light,medium,heavy=300 wood,steel,concrete=0
- **BSUB** Yuri Boomer · 载具 · 造价 2000 · 血 1200 · heavy · 速 5 · 视野 8 · 前提 YAYARD,RADAR · 等级 2 · BoomerTorpedo(60伤/120帧/射程7 弹头APSplash2) · 每发 → none,flak,plate,medium,heavy,special_2=60 light=45 wood,steel=39 concrete=36 special_1=15
- **SCHP** Soviet Siege Chopper · 载具 · 造价 1100 · 血 300 · light · 速 12 · 视野 7 · 前提 NAWEAP,TECH · 等级 7 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25
- **MIND** Master Mind · 载具 · 造价 1750 · 血 500 · heavy · 速 4 · 视野 9 · 前提 YAWEAP,YATECH · 等级 2 · MultipleMindControlTank(3伤/10帧/射程6 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=3 wood,steel,concrete=0
- **DISK** Floating Disk · 载具 · 造价 1750 · 血 600 · light · 速 15 · 视野 9 · 前提 YAWEAP,YATECH · 等级 2 · DiskLaser(90伤/80帧/射程7 弹头DiskWH) · 每发 → none,flak,plate,wood,steel,concrete,special_1,special_2=90 light,medium,heavy=45
- **ROBO** Robot Tank · 载具 · 造价 600 · 血 180 · heavy · 速 10 · 视野 6 · 前提 GAWEAP,GAROBO · 等级 2 · Robogun(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39

### 飞行器（2）

- **ORCA** Intruder · 飞行器 · 造价 1200 · 血 150 · light · 速 14 · 视野 8 · 前提 RADAR · 等级 3 · Maverick(150伤/10帧/射程6 弹头ORCAAP) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=150 concrete=112.5
- **BEAG** Black Eagle · 飞行器 · 造价 1200 · 血 200 · light · 速 14 · 视野 8 · 前提 RADAR · 等级 3 · Maverick2(200伤/10帧/射程6 弹头ORCAAP) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=200 concrete=150

## 其它（81）

### 步兵（34）

- **CIV1** Civilian · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIV2** Civilian · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIV3** Civilian · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CTECH** Technician · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **WEEDGUY** ZZZ Chem Spray Infantry · 步兵 · 造价 300 · 血 130 · none · 速 6 · 视野 4 · 前提 BARRACKS · 等级 -1 · NukeCarrier(0伤/1帧/射程0 弹头NukeMaker) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **COW** Animal Cow · 步兵 · 造价 10 · 血 150 · none · 速 4 · 视野 4 · 等级 -1
- **ALL** Animal Alligator · 步兵 · 造价 10 · 血 200 · none · 速 4 · 视野 2 · 等级 -1 · AlligatorBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **VLADIMIR** Vladimir · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **PENTGEN** General Pentagon · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **PRES** President · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **SSRV** Secret Service · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVA** Civilian Texan A · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVB** Civilian Texan B · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVC** Civilian Texan C · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVBBP** Civilian Baseball Player · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBFM** Civilian Beach Fat Male · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBF** Civilian Beach Female · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBTM** Civilian Beach Thin Male · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSFM** Civilian Snow Fat Male · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSF** Civilian Snow Female · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSTM** Civilian Snow Thin Male · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **POLARB** Animal Polar Bear · 步兵 · 造价 10 · 血 200 · none · 速 4 · 视野 2 · 等级 -1 · BearBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **JOSH** Animal Monkey · 步兵 · 造价 10 · 血 200 · none · 速 6 · 视野 2 · 等级 -1 · ChimpBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **CLNT** Cowboy · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · CLINTGUN(125伤/10帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **ARND** Hero · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · TERMIGUN(125伤/5帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **STLN** Bodybuilder · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · STALGUN(125伤/10帧/射程6 弹头HollowPoint4) · 每发 → none,flak,plate,special_1,special_2=125 light,medium,heavy,wood,steel,concrete=0
- **CAML** Animal Camel · 步兵 · 造价 10 · 血 200 · none · 速 6 · 视野 2 · 等级 -1
- **EINS** Albert Einstein · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **MUMY** Evil Mummy · 步兵 · 造价 100 · 血 400 · plate · 速 3 · 视野 6 · 等级 -1 · Mummypunch(100伤/60帧/射程0 弹头Battering) · 每发 → none,flak,plate,special_2=100 light,medium,heavy=0 wood,steel=30 concrete=20 special_1=200
- **RMNV** Romanov · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **DNOA** Animal T-Rex · 步兵 · 造价 2700 · 血 300 · Plate · 速 8 · 视野 5 · 等级 -1 · TRexInfBite(200伤/30帧/射程0 弹头TRexInfWH) · 每发 → none=200 flak=180 plate=160 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **DNOB** Animal Bront · 步兵 · 造价 1000 · 血 200 · light · 速 8 · 视野 5 · 等级 -1 · ChimpBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **SLAV** Yuri Slave Worker · 步兵 · 造价 10 · 血 125 · none · 速 3 · 视野 5 · 等级 -1 · SHOVEL(30伤/30帧/射程0 弹头SA) · 每发 → none,special_1,special_2=30 flak,plate=24 light,steel=15 medium,heavy,concrete=7.5 wood=22.5
- **WWLF** Werewolf · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1

### 载具（38）

- **CAR** Automobile · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **BUS** School Bus · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **WINI** Recreational Vehicle · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **PICK** Pickup Truck · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **HORV** War Miner · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 等级 -1
- **TRUCKA** Truck · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 5 · 等级 -1
- **TRUCKB** Truck (loaded) · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 5 · 等级 -1
- **HOWI** Howitzer · 载具 · 造价 750 · 血 200 · light · 速 5 · 视野 8 · 前提 GAWEAP · 等级 -1 · HowitzerGun(75伤/100帧/射程12 弹头HowitzerWH) · 每发 → none,special_2=75 flak=67.5 plate,special_1=60 light=45 medium,heavy,steel=30 wood=37.5 concrete=18.75
- **HIND** Hind Transport · 载具 · 造价 1000 · 血 300 · light · 速 15 · 视野 7 · 前提 NAWEAP · 等级 -1 · 载员 10 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25
- **CMON** Chrono Miner(noback) · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 等级 -1
- **XCOMET** Placeholder · 载具 · 造价 2000 · 血 300 · heavy · 速 4 · 视野 8 · 前提 GAWEAP,GATECH · 等级 -1 · CometFragment(30伤/120帧/射程3 弹头CometWH) · 每发 → none,flak,plate,special_1,special_2=30 light=22.5 medium,heavy=15 wood,steel,concrete=60
- **DeathDummy** DeathDummy · 载具 · 造价 0 · 血 0 · none · 速 0 · 视野 0 · 等级 -1 · DefaultDeathWeapon(0伤/1帧/射程0 弹头DeathWH) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **VLAD** Vladimir's Dreadnought · 载具 · 造价 2500 · 血 1500 · heavy · 速 8 · 视野 8 · 前提 NAYARD,NATECH · 等级 -1 · DredLauncher(50伤/50帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=50
- **PROPA** Propaganda Truck · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **CONA** Construction Excavator · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **COP** Police Car · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **EUROC** European Car A · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **LIMO** Limo · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **STANG** Sports Car · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **SUVB** SUV Black · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **SUVW** SUV White · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **TAXI** Taxi · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **PTRUCK** Pickup Truck · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CRUISE** Cruise Ship · 载具 · 造价 0 · 血 300 · light · 速 4 · 视野 8 · 前提 NAWEAP · 等级 -1
- **TUG** Tug Boat · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CDEST** Coast Guard Boat · 载具 · 造价 1000 · 血 600 · light · 速 6 · 视野 7 · 等级 -1 · 155mm(60伤/110帧/射程8 弹头ARTYHE) · 每发 → none,light,wood,steel,special_1,special_2=60 flak=48 plate,medium,heavy,concrete=36
- **SMON** ZZZ Useless · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 等级 -1
- **YCAB** Yellow Cab · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **DDBX** Double Decker Bus · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **BCAB** Black Cab · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **JEEP** Jeep · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **UTNK** ZZZ Not Used · 载具 · 造价 1000 · 血 400 · heavy · 速 6 · 视野 8 · 前提 NAWEAP · 等级 -1 · Comet(100伤/100帧/射程10 弹头CometWH) · 每发 → none,flak,plate,special_1,special_2=100 light=75 medium,heavy=50 wood,steel,concrete=200
- **SCHD** ZZZ Deployed Soviet Siege Chopper · 载具 · 造价 1000 · 血 200 · light · 速 12 · 视野 7 · 前提 NAWEAP · 等级 -1 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25
- **DOLY** Hollywood Camera Dolly · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CBLC** Cable Car · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **FTRK** Fire Truck · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **AMBU** Ambulance · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CIVP** Civilian Plane · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1

### 飞行器（9）

- **HORNET** Hornet · 飞行器 · 造价 50 · 血 75 · light · 速 12 · 视野 2 · 等级 -1 · HornetBomb(40伤/3帧/射程5 弹头ORCAAP) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=40 concrete=30
- **V3ROCKET** V3 Rocket · 飞行器 · 造价 50 · 血 50 · special_2 · 速 15 · 视野 1 · 等级 -1
- **ASW** Osprey · 飞行器 · 造价 50 · 血 30 · light · 速 12 · 视野 2 · 等级 -1 · ASWBomb(50伤/3帧/射程3 弹头APSplash) · 每发 → none,flak,plate,special_1=12.5 light=37.5 medium,heavy,special_2=50 wood,steel=32.5 concrete=30
- **DMISL** Dread Missile · 飞行器 · 造价 50 · 血 50 · special_2 · 速 18 · 视野 0 · 等级 -1
- **PDPLANE** Cargo Plane · 飞行器 · 造价 0 · 血 400 · light · 速 15 · 视野 0 · 等级 -1 · ParaDropWeapon(60伤/130帧/射程4 弹头MaverickHE) · 每发 → none,flak,plate,special_1=15 light,wood,special_2=60 medium,heavy,concrete=30 steel=45
- **CARGOPLANE** Transport Plane · 飞行器 · 造价 0 · 血 400 · light · 速 15 · 视野 0 · 等级 -1
- **BPLN** Soviet MIG · 飞行器 · 造价 0 · 血 200 · light · 速 16 · 视野 0 · 等级 -1 · Maverick3(750伤/10帧/射程4 弹头MIGWH) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=750 concrete=375
- **SPYP** Soviet Spy Plane · 飞行器 · 造价 0 · 血 600 · light · 速 15 · 视野 0 · 等级 -1 · SpyCameraWeapon(6伤/1帧/射程20 弹头DummyWarhead) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **CMISL** Cruise Missile · 飞行器 · 造价 50 · 血 50 · special_2 · 速 20 · 视野 0 · 等级 -1
