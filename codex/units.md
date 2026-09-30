# 单位

由 `corpus/raw/rulesmd.ini` 生成，共 155 个：可建造 74：盟军共用 22、苏军共用 18、尤里共用 14、跨阵营 10、国家特有 9；其它（民用、任务用）73，未使用 6。不要手改。

**先看自己是哪个国家**：阵营章只有该阵营的共用单位，各国特有的在 [`countries.md`](countries.md)。

「每发 →」是主武器对每种装甲的每次开火伤害，同值的并成一档；装甲代号顺序同 `corpus/derived/rules.json` 的 `armor_types`。

## 盟军（GDI）（22）

- **E1** GI（美国大兵） · 步兵 · 造价 200 · 血 125 · none · 速 4 · 视野 5 · 前提 GAPILE · 等级 1 · M60(15伤/20帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **JUMPJET** Rocketeer（火箭飞行兵） · 步兵 · 造价 600 · 血 125 · none · 速 9 · 视野 8 · 前提 GAPILE,RADAR · 等级 3 · 20mm(25伤/30帧/射程5 弹头SSA) · 每发 → none,flak,plate,special_1,special_2=25 light=15 medium,heavy=10 wood=18.75 steel=12.5 concrete=6.25
- **GHOST** SEAL（海豹部队） · 步兵 · 造价 1000 · 血 125 · flak · 速 5 · 视野 8 · 前提 GAPILE,RADAR · 等级 9 · MP5(125伤/10帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **CLEG** Chrono Legionnaire（超时空军团兵） · 步兵 · 造价 1500 · 血 125 · none · 速 5 · 视野 8 · 前提 GAPILE,TECH · 等级 10 · NeutronRifle(8伤/120帧/射程5 弹头ChronoBeam) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1=8 special_2=0
- **SPY** Spy（间谍） · 步兵 · 造价 1000 · 血 100 · flak · 速 4 · 视野 9 · 前提 GAPILE,GATECH · 等级 5 · MakeupKit(1伤/100帧/射程-2 弹头Snapshot) · 每发 → none,flak,plate,special_1,special_2=1 light,medium,heavy,wood,steel,concrete=0
- **TANY** Tanya（谭雅） · 步兵 · 造价 1500 · 血 200 · flak · 速 6 · 视野 8 · 前提 GAPILE,GATECH · 等级 9 · DoublePistols(125伤/5帧/射程6 弹头HollowPoint2) · 每发 → none,flak,plate,special_2=125 light,medium,heavy=0 wood,steel,concrete,special_1=1.25
- **GGI** Guardian GI（重装大兵） · 步兵 · 造价 400 · 血 100 · none · 速 3 · 视野 6 · 前提 GAPILE · 等级 2 · M60(15伤/20帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **AMCV** Allied Construction Vehicle（盟军基地车） · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 6 · 前提 GAWEAP,GADEPT · 等级 10
- **MTNK** Grizzly Battle Tank（灰熊坦克） · 载具 · 造价 700 · 血 300 · heavy · 速 7 · 视野 8 · 前提 GAWEAP · 等级 2 · 105mm(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39
- **CARRIER** Aircraft Carrier（航空母舰） · 载具 · 造价 2000 · 血 800 · heavy · 速 4 · 视野 7 · 前提 GAYARD,TECH · 等级 7 · HornetLauncher(1伤/150帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **DEST** Destroyer（驱逐舰） · 载具 · 造价 1000 · 血 600 · heavy · 速 6 · 视野 7 · 前提 GAYARD · 等级 4 · 155mm(60伤/110帧/射程8 弹头ARTYHE) · 每发 → none,light,wood,steel,special_1,special_2=60 flak=48 plate,medium,heavy,concrete=36
- **AEGIS** Aegis Cruiser（神盾巡洋舰） · 载具 · 造价 1200 · 血 800 · light · 速 4 · 视野 8 · 前提 GAYARD,RADAR · 等级 7 · Medusa(100伤/15帧/射程12 弹头SAMWH) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=100 wood,steel,concrete=0
- **LCRF** Landing Craft（盟军气垫艇） · 载具 · 造价 900 · 血 300 · light · 速 6 · 视野 6 · 前提 GAYARD · 等级 4 · 载员 12
- **SHAD** BlackHawk Transport（夜鹰直升机） · 载具 · 造价 1000 · 血 175 · light · 速 14 · 视野 7 · 前提 GAWEAP · 等级 7 · 载员 5 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25
- **DLPH** Dolphin（海豚） · 载具 · 造价 500 · 血 200 · light · 速 8 · 视野 4 · 前提 GAYARD,GATECH · 等级 5 · SonicZap(4伤/120帧/射程6 弹头SonicWarhead) · 每发 → none,flak,plate,light,wood,special_1,special_2=4 medium,heavy=3.2 steel,concrete=2.4
- **CMIN** Chrono Miner（超时空矿车） · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 前提 GAWEAP,PROC · 等级 1
- **SREF** Prism Tank（光陵坦克） · 载具 · 造价 1200 · 血 150 · light · 速 4 · 视野 8 · 前提 GAWEAP,GATECH · 等级 8
- **MGTK** Mirage Tank（幻影坦克） · 载具 · 造价 1000 · 血 200 · light · 速 7 · 视野 9 · 前提 GAWEAP,GATECH · 等级 9 · MirageGun(100伤/70帧/射程7 弹头MirageWH) · 每发 → none,flak,light,medium,heavy,special_1,special_2=100 plate=80 wood=30 steel,concrete=20
- **FV** IFV（多功能步兵车） · 载具 · 造价 600 · 血 200 · light · 速 10 · 视野 8 · 前提 GAWEAP · 等级 3 · 载员 1 · HoverMissile(25伤/50帧/射程6 弹头HE) · 每发 → none,flak,plate,special_2=25 light,medium=17.5 heavy=8.75 wood=18.75 steel=10 concrete=5 special_1=20
- **BFRT** Battle Fortress（战斗要塞） · 载具 · 造价 2000 · 血 600 · heavy · 速 4 · 视野 6 · 前提 GAWEAP,GATECH · 等级 10 · 载员 5 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **ROBO** Robot Tank（机器人坦克） · 载具 · 造价 600 · 血 180 · heavy · 速 10 · 视野 6 · 前提 GAWEAP,GAROBO · 等级 2 · Robogun(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39
- **ORCA** Intruder（入侵者战机） · 飞行器 · 造价 1200 · 血 150 · light · 速 14 · 视野 8 · 前提 RADAR · 等级 3 · 禁 Alliance · Maverick(150伤/10帧/射程6 弹头ORCAAP) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=150 concrete=112.5

## 苏军（Nod）（18）

- **E2** Conscript（动员兵） · 步兵 · 造价 100 · 血 125 · flak · 速 4 · 视野 5 · 前提 NAHAND · 等级 1 · M1Carbine(15伤/25帧/射程4 弹头SA) · 每发 → none,special_1,special_2=15 flak,plate=12 light,steel=7.5 medium,heavy,concrete=3.75 wood=11.25
- **SHK** Shock Trooper（磁爆步兵） · 步兵 · 造价 500 · 血 130 · Plate · 速 4 · 视野 6 · 前提 NAHAND · 等级 5 · ElectricBolt(50伤/60帧/射程3 弹头Shock) · 每发 → none,flak,plate,medium,heavy,special_2=50 light=42.5 wood,steel,concrete=25 special_1=100
- **IVAN** Crazy Ivan（疯狂伊文） · 步兵 · 造价 600 · 血 125 · none · 速 4 · 视野 6 · 前提 NAHAND,NARADR · 等级 5 · IvanBomber(400伤/50帧/射程0 弹头IvanBomb) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=400
- **BORIS** Boris（鲍裏斯） · 步兵 · 造价 1500 · 血 200 · flak · 速 5 · 视野 9 · 前提 NAHAND,NATECH · 等级 9 · AKM(65伤/20帧/射程7 弹头BORISWH) · 每发 → none,flak=130 plate,special_1,special_2=65 light,medium,heavy=32.5 wood,steel,concrete=0.65
- **HARV** War Miner（苏军矿车） · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 前提 NAWEAP,PROC · 等级 1 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **APOC** Apocalypse（天启坦克） · 载具 · 造价 1750 · 血 800 · heavy · 速 4 · 视野 6 · 前提 NAWEAP,NATECH · 等级 7 · 120mmx(100伤/80帧/射程0 弹头ApocAP) · 每发 → none,flak,plate=25 light=75 medium,heavy,wood,steel,special_2=100 concrete=70 special_1=60
- **HTNK** Rhino Heavy Tank（犀牛坦克） · 载具 · 造价 900 · 血 400 · heavy · 速 6 · 视野 8 · 前提 NAWEAP · 等级 2 · 120mm(90伤/65帧/射程0 弹头AP) · 每发 → none,flak=22.5 plate=13.5 light=67.5 medium,heavy,special_2=90 wood=58.5 steel=40.5 concrete,special_1=54
- **SAPC** Armored Transport（苏军气垫船） · 载具 · 造价 900 · 血 300 · heavy · 速 6 · 视野 6 · 前提 NAYARD · 等级 2 · 载员 12
- **V3** V3 Launcher（飞弹） · 载具 · 造价 800 · 血 150 · light · 速 4 · 视野 7 · 前提 NAWEAP,NARADR · 等级 3 · V3Launcher(1伤/150帧/射程18 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **ZEP** Kirov Airship（基洛夫飞艇） · 载具 · 造价 2000 · 血 2000 · medium · 速 5 · 视野 8 · 前提 NAWEAP,NATECH · 等级 10 · BlimpBomb(250伤/50帧/射程0 弹头BlimpHE) · 每发 → none,flak,plate,special_1,special_2=250 light=175 medium,heavy=87.5 wood=212.5 steel=187.5 concrete=125
- **DRON** Terror Drone（恐怖机器人） · 载具 · 造价 500 · 血 100 · special_1 · 速 10 · 视野 4 · 前提 NAWEAP · 等级 4 · DroneJump(50伤/60帧/射程0 弹头Parasite) · 每发 → none,flak,plate,light,medium,heavy=50 wood,steel,concrete,special_1,special_2=0
- **HTK** Flak Track（防空车） · 载具 · 造价 500 · 血 180 · heavy · 速 8 · 视野 8 · 前提 NAWEAP · 等级 3 · 载员 5 · FlakTrackGun(25伤/25帧/射程5 弹头FlakTWH) · 每发 → none=37.5 flak=31.25 plate,special_1,special_2=25 light=15 medium,heavy,concrete=2.5 wood=7.5 steel=5
- **SUB** Typhoon Attack Sub（台风潜艇） · 载具 · 造价 1000 · 血 600 · heavy · 速 4 · 视野 4 · 前提 NAYARD · 等级 2 · SubTorpedo(100伤/120帧/射程7 弹头APSplash) · 每发 → none,flak,plate,special_1=25 light=75 medium,heavy,special_2=100 wood,steel=65 concrete=60
- **DRED** Dreadnought（无畏级战舰） · 载具 · 造价 2000 · 血 800 · heavy · 速 4 · 视野 7 · 前提 NAYARD,NATECH · 等级 6 · DredLauncher(50伤/50帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=50
- **SQD** Giant Squid（巨型乌贼） · 载具 · 造价 1000 · 血 200 · light · 速 8 · 视野 5 · 前提 NAYARD,NATECH · 等级 9 · SquidGrab(15伤/99帧/射程0 弹头ParasitePlus) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=15
- **SMCV** Soviet Construction Vehicle（苏军基地车） · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 6 · 前提 NAWEAP,NADEPT · 等级 10
- **HYD** Sea Scorpion（海蝎） · 载具 · 造价 600 · 血 400 · heavy · 速 8 · 视野 8 · 前提 NAYARD,NARADR · 等级 6 · FlakTrackGun(25伤/25帧/射程5 弹头FlakTWH) · 每发 → none=37.5 flak=31.25 plate,special_1,special_2=25 light=15 medium,heavy,concrete=2.5 wood=7.5 steel=5
- **SCHP** Soviet Siege Chopper（围攻直升机） · 载具 · 造价 1100 · 血 300 · light · 速 12 · 视野 7 · 前提 NAWEAP,TECH · 等级 7 · BlackHawkCannon(35伤/40帧/射程6 弹头SA) · 每发 → none,special_1,special_2=35 flak,plate=28 light,steel=17.5 medium,heavy,concrete=8.75 wood=26.25

## 尤里（ThirdSide）（14）

- **YURIPR** Yuri Prime（超级尤里） · 步兵 · 造价 1500 · 血 150 · flak · 速 6 · 视野 9 · 前提 YABRCK,YATECH · 等级 10 · SuperMindControl(1伤/200帧/射程7 弹头ControllerBuilding) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **INIT** Yuri Initiate（尤里新兵） · 步兵 · 造价 200 · 血 100 · none · 速 4 · 视野 9 · 前提 YABRCK · 等级 1 · PsychicJab(25伤/15帧/射程0 弹头SAFlame) · 每发 → none,special_1,special_2=25 flak,plate=20 light,steel=12.5 medium,heavy,concrete=6.25 wood=18.75
- **BRUTE** Yuri Brute（狂兽人） · 步兵 · 造价 500 · 血 200 · plate · 速 6 · 视野 8 · 前提 YABRCK · 等级 5 · Punch(100伤/60帧/射程0 弹头Battering) · 每发 → none,flak,plate,special_2=100 light,medium,heavy=0 wood,steel=30 concrete=20 special_1=200
- **VIRUS** Yuri Virus（病毒狙击手） · 步兵 · 造价 700 · 血 100 · none · 速 4 · 视野 9 · 前提 YABRCK,RADAR · 等级 1 · Virusgun(125伤/100帧/射程10 弹头Virus) · 每发 → none,flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **LTNK** Lasher Light Tank（狂风坦克） · 载具 · 造价 700 · 血 300 · heavy · 速 7 · 视野 8 · 前提 YAWEAP · 等级 2 · ATGUN(65伤/60帧/射程5 弹头AP) · 每发 → none,flak=16.25 plate=9.75 light=48.75 medium,heavy,special_2=65 wood=42.25 steel=29.25 concrete,special_1=39
- **YHVR** Hover Transport Yuri（尤里气垫船） · 载具 · 造价 900 · 血 300 · heavy · 速 6 · 视野 6 · 前提 YAYARD · 等级 2 · 载员 12
- **PCV** Yuri Construction Vehicle（尤里基地车） · 载具 · 造价 3000 · 血 1000 · heavy · 速 4 · 视野 8 · 前提 YAWEAP,YAGRND · 等级 10
- **SMIN** Slave Miner（奴隶矿车） · 载具 · 造价 1750 · 血 2000 · medium · 速 3 · 视野 4 · 前提 YAWEAP · 等级 1 · 20mmRapid(30伤/20帧/射程0 弹头HARVWH) · 每发 → none,special_2=30 flak=24 plate=21 light=15 medium,heavy,wood=6 steel=4.5 concrete=3 special_1=120
- **YTNK** Gattling Tank（格林机炮坦克） · 载具 · 造价 600 · 血 210 · light · 速 6 · 视野 10 · 前提 YAWEAP · 等级 4 · AGGattling(25伤/16帧/射程6 弹头GattWH) · 每发 → none=25 flak=20 plate=17.5 light,special_2=12.5 medium=7.5 heavy,wood=2.5 steel=1.25 concrete=0.75 special_1=50
- **TELE** Magnetron（磁电坦克） · 载具 · 造价 1000 · 血 150 · light · 速 5 · 视野 10 · 前提 YAWEAP,NAPSIS · 等级 2 · MagneticBeam(5000伤/20帧/射程12 弹头LocomotorBeam) · 每发 → none,flak,plate,wood,steel,concrete,special_2=0 light,medium,heavy,special_1=5000
- **CAOS** Chaos Drone（神经突击车） · 载具 · 造价 1000 · 血 130 · light · 速 8 · 视野 6 · 前提 YAWEAP · 等级 4 · ChaosAttack(600伤/45帧/射程3 弹头PsychGasCreate) · 每发 → none,flak,plate,special_1,special_2=600 light,medium,heavy=300 wood,steel,concrete=0
- **BSUB** Yuri Boomer（雷鸣潜艇） · 载具 · 造价 2000 · 血 1200 · heavy · 速 5 · 视野 8 · 前提 YAYARD,RADAR · 等级 2 · BoomerTorpedo(60伤/120帧/射程7 弹头APSplash2) · 每发 → none,flak,plate,medium,heavy,special_2=60 light=45 wood,steel=39 concrete=36 special_1=15
- **MIND** Master Mind（策划者） · 载具 · 造价 1750 · 血 500 · heavy · 速 4 · 视野 9 · 前提 YAWEAP,YATECH · 等级 2 · MultipleMindControlTank(3伤/10帧/射程6 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=3 wood,steel,concrete=0
- **DISK** Floating Disk（镭射幽浮） · 载具 · 造价 1750 · 血 600 · light · 速 15 · 视野 9 · 前提 YAWEAP,YATECH · 等级 2 · DiskLaser(90伤/80帧/射程7 弹头DiskWH) · 每发 → none,flak,plate,wood,steel,concrete,special_1,special_2=90 light,medium,heavy=45

## 跨阵营（10）

- **ENGINEER** Engineer（盟军工程师） · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · 禁 Russians,Confederation,Africans,Arabs,YuriCountry · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **YURI** Yuri Clone（克隆尤里） · 步兵 · 造价 800 · 血 100 · none · 速 4 · 视野 12 · 前提 YABRCK,NAPSIS · 等级 10 · MindControl(1伤/200帧/射程7 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=1 wood,steel,concrete=0
- **DOG** Attack Dog（苏军警犬） · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 Barracks · 等级 2 · 禁 British,French,Germans,Americans,Alliance,YuriCountry · BadTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **CCOMAND** Chrono Commando（超时空突击队） · 步兵 · 造价 2000 · 血 100 · none · 速 5 · 视野 8 · 前提 BARRACKS · 等级 9 · 需窃取盟军科技 · ChronoMP5(125伤/10帧/射程6 弹头HollowPointNoBuilding) · 每发 → none=250 flak,special_2=125 plate,special_1=93.75 light,medium,heavy=1.25 wood,steel,concrete=0
- **PTROOP** Psi-Corp Trooper（心灵突击队） · 步兵 · 造价 1000 · 血 100 · none · 速 5 · 视野 8 · 前提 BARRACKS · 等级 9 · 需窃取尤里科技 · MindControl(1伤/200帧/射程7 弹头Controller) · 每发 → none,flak,plate,light,medium,heavy,special_1,special_2=1 wood,steel,concrete=0
- **CIVAN** Chrono Ivan（超时空伊文） · 步兵 · 造价 1750 · 血 100 · none · 速 6 · 视野 8 · 前提 BARRACKS · 等级 9 · 需窃取苏军科技 · IvanBomber(400伤/50帧/射程0 弹头IvanBomb) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=400
- **FLAKT** Flak Trooper（防空步兵） · 步兵 · 造价 300 · 血 100 · none · 速 4 · 视野 5 · 前提 NAHAND,NARADR · 等级 1 · FlakGuyGun(20伤/20帧/射程5 弹头FlakTWH) · 每发 → none=30 flak=25 plate,special_1,special_2=20 light=12 medium,heavy,concrete=2 wood=6 steel=4
- **SENGINEER** Soviet Engineer（苏军工程师） · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · 禁 British,French,Germans,Americans,Alliance,YuriCountry · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1
- **ADOG** Allied Attack Dog（盟军警犬） · 步兵 · 造价 200 · 血 100 · none · 速 8 · 视野 9 · 前提 Barracks · 等级 2 · 禁 Russians,Confederation,Africans,Arabs,YuriCountry · GoodTeeth(30伤/30帧/射程0 弹头ParasiteDog) · 每发 → none,flak,plate=30 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **YENGINEER** Yuri Engineer（尤里工程师） · 步兵 · 造价 500 · 血 75 · none · 速 4 · 视野 4 · 前提 Barracks · 等级 1 · 禁 British,French,Germans,Americans,Alliance,Russians,Confederation,Africans,Arabs · DefuseKit(1伤/20帧/射程0 弹头BombDisarm) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=1

## 民用与其它（73）

- **CIV1** Civilian（平民） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIV2** Civilian（白衣服） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIV3** Civilian（技师） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CTECH** Technician（苏联卫兵） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **COW** Animal Cow（奶牛） · 步兵 · 造价 10 · 血 150 · none · 速 4 · 视野 4 · 等级 -1
- **ALL** Animal Alligator（鄂鱼） · 步兵 · 造价 10 · 血 200 · none · 速 4 · 视野 2 · 等级 -1 · AlligatorBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **VLADIMIR** Vladimir（黄衣服将军） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **PENTGEN** General Pentagon（绿衣服将军） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **PRES** President（总统） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **SSRV** Secret Service（终级保镖） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVA** Civilian Texan A（工人样） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVB** Civilian Texan B（牛仔） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVC** Civilian Texan C（黑衣蓝裤） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1 · Pistola(2伤/20帧/射程3 弹头SA) · 每发 → none,special_1,special_2=2 flak,plate=1.6 light,steel=1 medium,heavy,concrete=0.5 wood=1.5
- **CIVBBP** Civilian Baseball Player（棒球员） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBFM** Civilian Beach Fat Male（海滩胖男） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBF** Civilian Beach Female（海滩女） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVBTM** Civilian Beach Thin Male（海滩瘦男） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSFM** Civilian Snow Fat Male（老人） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSF** Civilian Snow Female（红衣服女） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CIVSTM** Civilian Snow Thin Male（黑衣服） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **POLARB** Animal Polar Bear（北极熊） · 步兵 · 造价 10 · 血 200 · none · 速 4 · 视野 2 · 等级 -1 · BearBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **JOSH** Animal Monkey（猴） · 步兵 · 造价 10 · 血 200 · none · 速 6 · 视野 2 · 等级 -1 · ChimpBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **CLNT** Cowboy（快枪手） · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · CLINTGUN(125伤/10帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **ARND** Hero（终结者） · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · TERMIGUN(125伤/5帧/射程6 弹头HollowPoint) · 每发 → none=250 flak,plate,special_2=125 light,medium,heavy,wood,steel,concrete,special_1=1.25
- **STLN** Bodybuilder（蓝波） · 步兵 · 造价 10 · 血 200 · plate · 速 6 · 视野 2 · 等级 -1 · STALGUN(125伤/10帧/射程6 弹头HollowPoint4) · 每发 → none,flak,plate,special_1,special_2=125 light,medium,heavy,wood,steel,concrete=0
- **CAML** Animal Camel（骆驼） · 步兵 · 造价 10 · 血 200 · none · 速 6 · 视野 2 · 等级 -1
- **EINS** Albert Einstein（爱因斯坦） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **MUMY** Evil Mummy（木乃伊） · 步兵 · 造价 100 · 血 400 · plate · 速 3 · 视野 6 · 等级 -1 · Mummypunch(100伤/60帧/射程0 弹头Battering) · 每发 → none,flak,plate,special_2=100 light,medium,heavy=0 wood,steel=30 concrete=20 special_1=200
- **RMNV** Romanov（洛马诺夫总理） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **DNOA** Animal T-Rex（暴龙） · 步兵 · 造价 2700 · 血 300 · Plate · 速 8 · 视野 5 · 等级 -1 · TRexInfBite(200伤/30帧/射程0 弹头TRexInfWH) · 每发 → none=200 flak=180 plate=160 light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **DNOB** Animal Bront（腕龙） · 步兵 · 造价 1000 · 血 200 · light · 速 8 · 视野 5 · 等级 -1 · ChimpBite(30伤/30帧/射程0 弹头HollowPoint) · 每发 → none=60 flak,plate,special_2=30 light,medium,heavy,wood,steel,concrete,special_1=0.3
- **SLAV** Yuri Slave Worker（奴隶矿工） · 步兵 · 造价 10 · 血 125 · none · 速 3 · 视野 5 · 等级 -1 · SHOVEL(30伤/30帧/射程0 弹头SA) · 每发 → none,special_1,special_2=30 flak,plate=24 light,steel=15 medium,heavy,concrete=7.5 wood=22.5
- **WWLF** Werewolf（狼人（未使用）） · 步兵 · 造价 10 · 血 50 · none · 速 4 · 视野 2 · 等级 -1
- **CAR** Automobile（汽车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **BUS** School Bus（校车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **WINI** Recreational Vehicle（野营车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **PICK** Pickup Truck（小货车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **HORV** War Miner（苏军矿车(倒矿)） · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 等级 -1
- **TRUCKA** Truck（卡车） · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 5 · 等级 -1
- **TRUCKB** Truck (loaded)（卡车(载货)） · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 5 · 等级 -1
- **CMON** Chrono Miner(noback)（超时空矿车(倒矿)） · 载具 · 造价 1400 · 血 1000 · medium · 速 4 · 视野 4 · 等级 -1
- **VLAD** Vladimir's Dreadnought（维拉迪摩指挥舰） · 载具 · 造价 2500 · 血 1500 · heavy · 速 8 · 视野 8 · 前提 NAYARD,NATECH · 等级 -1 · 禁 Russians · DredLauncher(50伤/50帧/射程25 弹头Special) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=50
- **PROPA** Propaganda Truck（宣传车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **CONA** Construction Excavator（挖土机） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **COP** Police Car（警车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **EUROC** European Car A（黑色） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **LIMO** Limo（豪华轿车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **STANG** Sports Car（跑车型） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **SUVB** SUV Black（包厢型） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **SUVW** SUV White（包厢型） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **TAXI** Taxi（计程车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **PTRUCK** Pickup Truck（皮卡型） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CRUISE** Cruise Ship（游船） · 载具 · 造价 0 · 血 300 · light · 速 4 · 视野 8 · 前提 NAWEAP · 等级 -1
- **TUG** Tug Boat（拖船） · 载具 · 造价 0 · 血 200 · light · 速 4 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CDEST** Coast Guard Boat（海岸巡逻船） · 载具 · 造价 1000 · 血 600 · light · 速 6 · 视野 7 · 等级 -1 · 155mm(60伤/110帧/射程8 弹头ARTYHE) · 每发 → none,light,wood,steel,special_1,special_2=60 flak=48 plate,medium,heavy,concrete=36
- **YCAB** Yellow Cab（黄色计程车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **DDBX** Double Decker Bus（巴士） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1 · 载员 5
- **BCAB** Black Cab（黑色计程车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **JEEP** Jeep（吉普车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **DOLY** Hollywood Camera Dolly（摄影车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CBLC** Cable Car（电车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **FTRK** Fire Truck（救火车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **AMBU** Ambulance（救护车） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **CIVP** Civilian Plane（民用飞机） · 载具 · 造价 0 · 血 100 · light · 速 8 · 视野 8 · 前提 NAWEAP · 等级 -1
- **HORNET** Hornet（苏军气垫船） · 飞行器 · 造价 50 · 血 75 · light · 速 12 · 视野 2 · 等级 -1 · HornetBomb(40伤/3帧/射程5 弹头ORCAAP) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=40 concrete=30
- **V3ROCKET** V3 Rocket（火箭） · 飞行器 · 造价 50 · 血 50 · special_2 · 速 15 · 视野 1 · 等级 -1
- **ASW** Osprey（舰载反潜机） · 飞行器 · 造价 50 · 血 30 · light · 速 12 · 视野 2 · 等级 -1 · ASWBomb(50伤/3帧/射程3 弹头APSplash) · 每发 → none,flak,plate,special_1=12.5 light=37.5 medium,heavy,special_2=50 wood,steel=32.5 concrete=30
- **DMISL** Dread Missile（无畏级导弹） · 飞行器 · 造价 50 · 血 50 · special_2 · 速 18 · 视野 0 · 等级 -1
- **PDPLANE** Cargo Plane（运输机） · 飞行器 · 造价 0 · 血 400 · light · 速 15 · 视野 0 · 等级 -1 · ParaDropWeapon(60伤/130帧/射程4 弹头MaverickHE) · 每发 → none,flak,plate,special_1=15 light,wood,special_2=60 medium,heavy,concrete=30 steel=45
- **CARGOPLANE** Transport Plane（伞兵运输机） · 飞行器 · 造价 0 · 血 400 · light · 速 15 · 视野 0 · 等级 -1
- **BPLN** Soviet MIG（米格战机） · 飞行器 · 造价 0 · 血 200 · light · 速 16 · 视野 0 · 等级 -1 · Maverick3(750伤/10帧/射程4 弹头MIGWH) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,special_1,special_2=750 concrete=375
- **SPYP** Soviet Spy Plane（间谍飞机） · 飞行器 · 造价 0 · 血 600 · light · 速 15 · 视野 0 · 等级 -1 · SpyCameraWeapon(6伤/1帧/射程20 弹头DummyWarhead) · 每发 → none,flak,plate,light,medium,heavy,wood,steel,concrete,special_1,special_2=0
- **CMISL** Cruise Missile（海岸巡逻船） · 飞行器 · 造价 50 · 血 50 · special_2 · 速 20 · 视野 0 · 等级 -1

## 战役特供（1）

科技等级超过 10，正常对战里造不出来。

- **LUNR** Lunar Infantry（月球飞行兵） · 步兵 · 造价 600 · 血 125 · none · 速 9 · 视野 8 · 前提 NAPILE,RADAR · 等级 11 · Lunarlaser(25伤/20帧/射程7 弹头LUNARWH) · 每发 → none,flak,plate,wood,steel,concrete,special_1,special_2=25 light=18.75 medium,heavy=12.5

## 未使用（6）

引擎用名字前缀 `ZZZ` 标注，留着只为了表里没有悬空引用。

- **WEEDGUY** ZZZ Chem Spray Infantry
- **XCOMET** Placeholder
- **DeathDummy** DeathDummy
- **SMON** ZZZ Useless
- **UTNK** ZZZ Not Used
- **SCHD** ZZZ Deployed Soviet Siege Chopper
