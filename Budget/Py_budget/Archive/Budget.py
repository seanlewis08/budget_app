import pandas as pd
import numpy as np
from datetime import datetime as dt

class BudgetAnalyzer:
    def __init__(self, file_path):
        self.file_path = file_path
        self.ytd_data = self.read_data()

    def read_data(self):
        ytd_data = pd.read_csv(self.file_path)
        return ytd_data

    def format_date(self):
        self.ytd_data['Sort_Date'] = pd.to_datetime(self.ytd_data['Trans. Date'], format='%m/%d/%Y')
        self.ytd_data['Date'] = self.ytd_data['Sort_Date'].dt.strftime('%m/%Y')
        self.ytd_data.reset_index(drop=False, inplace=True)

    def map_transactions(self):
        mapping = {
            # Bills for Physical Property
            'payment': ['payment','RETURNED INTERNET PMT'],
            'interest': ['interest'],
            'cashback_bonus': ['cashback'],
            # Helping others
            'tahjei': ['the UPS store'],
            'jayelin': ['CYANFACE'],
            'don': ['justina'],
            'dad': ['gift', 'AF\*REAL'],

            # Bills for Physical Property
            'cell_phone': ['tmobile'],
            'state_farm': ['state farm'],
            'aps': ['Arizonapub'],
            'gym': ['planet fitness', 'life time'],
            'car': ['COBBLESTONE AUTO SPA 51 PHOENIX AZ', 'AT THE SHOP SAN MATEO CA', 'CLEAN FREAK - THOMAS PHOENIX AZ',
                    'TAKE 5 #667 PHOENIX AZ', 'autozone', 'dmv', 'NISSAN OF BURLINGAME BURLINGAME CA', 'OIL CHANGER',
                    "WWW.DIGISTORE24.COM - 8003567947 FL", "auto parts"],
            'dump': ['blue line'],

            # Bills for Essentials
            'groceries': ['safeway', 'whole', 'market', 'giant', 'frys', 'albertsons', 'Food City', 'Ralphs',
                          'NATURAL GROCERS PI PHOENIX AZ', 'INSTACART', "DEAN'S PRODUCE", "YOLO FRUIT STAND", "TRADER JOE",
                          "Sprouts Farmers", "harristeeter", "99 ranch", 'LUCKY #748','SHIPT','A.D.P DEPALMA FARM SAN FRANCISCOCA0001152921513049170106','THAO FAMILY FARM SAN FRANCISCOCA0001152921513049149557'],
            'amazon': ['amzn'],
            'barbershop': ['barb', "COASTAL CURL"],
            'taxes': ['FREETAXUSA.COM 877-2699027 UT'],

            # Bills for Discretionary Food Spending
            'fast_food': ['dunkin', 'taco', 'mcdonald', 'Jimmy', 'cafe rio', 'glow tea', 'pizza', 'pollo', 'nora asian',
                          'wow wow', 'burger king', 'panda',
                          'panda express', 'STARBIRD FOSTER CITY CA', 'HOLY GELATO',
                          'WHATABURGER', 'pokitrition', 'carls jr', 'cafe', 'in n out', 'five guys', 'doordash', 'chipotle',
                          'taco bell', 'subway', 'pita pit',
                          'sosoba', 'jersey mikes', 'cheba hut', 'cereal killerz', 'ike', 'fatty dad', 'tous les', 'atl wings',
                          '5guys', 'ocotillo',
                          'beach liquors', 'Big Papa', 'bosa donuts', 'tpumps', 'sweets 4 treats',
                          'TWO HIPPIES BEACH HOUSE PHOENIX AZ', 'KFC', 'STANFORDSTADIUMCONCESSIO', 'JACK IN THE BOX',
                          'CKE*SOM TUM STATION', "\*HOWIE'S ARTISAN PIZZ", "Nick the Greek", "Popeyes",
                          "8CHICK-FIL-A #04448 DALY CITY CA"],
            'restaurant': ['olive', 'seven mile', 'crack shack', 'haus', 'charlie', 'rotten john', 'pier', 'ollie', 'mekong',
                           'valley bar', 'bop', 'breakfast',
                           'crescent', 'thai basil', 'happy', 'la parrilla', 'ramen', 'first watch', 'endgame', 'grill',
                           'postino', 'bob & edith', 'meat pies',
                           'tom douglas', 'teaspoon', 'whining', '2LEVY@BANK1 PHOENIX AZ', 'slice', 'lebanese', 'noodles',
                           'superstition meader', 'union 76',
                           'PIZZERIA BIANCO PHOENIX AZ', 'SIZZLE KOREAN BBQ PHOENIX AZ', 'OREGANOS 1028 SCOTTSDALE AZ', 'FOGO',
                           'THE THEODORE PHOENIX AZ', "RISE PIZZERIA BURLINGAME", "ICICLES - MOUNTAIN MOUNTAIN VIEWCA",
                           "URBAN RITUAL SAN MATEO", "SALT & STRAW SAN JOSE", "ROYAL DONUT BURLINGAME",
                           "OLDE TYME KETTLE K FRESNO", "GOTHAM ENTERPRISE SAN", "GELATAIO SAN CARLOS", "CHERIMOYA BURLINGAME",
                           "FRANK GRIZZLY", "ARIZMENDI BAKERY C SAN", "WAHLBURGERS BURLINGAME BURLINGAME CA", "CREPEVINE",
                           "RASPADOS Y ANTOJITAS LA", "ANCHOR PUBLIC TAPS SAN FRANCISCOCA", "ASIAN BOX BURLINGAME CA",
                           "AYTTHAYA THAI SEATTLE WA", "OLD SPAGHETTI FACTORY", "SOL SCOTTSDALE", "KJ'S BAR SEATTLE",
                           "HONG KONG BANJUM PAIK'S", "HAN SUNG BBQ", "ALHAMBRA IRISH HOUSE", "THE PLANING MILL", "HABIT",
                           "THE NEW STAND", 'SFO THE PLANT', 'HYATT REG PHOENIX F&B', 'FLIGHTS BURLINGAME', 'COCOLA',
                           'BRUNDAVAN INDIAN CUISINE', 'APPLE FRITTER', 'INMOTION-814', 'NEW ERITREA',
                           'CHUKAR CHERRY COMPANY SEATTLE WA', 'jack\'s fish', 'maryvale', 'tony', 'GUANAQUITO RESTAURANT',
                           'MANNA SAN FRANCISCOCA', 'DISH N DASH 1ST SAN JOSE CA', 'MANNA SAN FRANCISCOCA',
                           'SQ \*SUAVECITO BIRRIA', 'MEET FRESH', 'JAMIES PLACE SAN FRANCISCOCA',
                           'SQ \*URLBINGAME BURLINGAME CA0001152921512317149246', "SMOKING GUN", "Dive Bar & Grill",
                           "Copenhagen Bakery", "Donut Bar", "Mama Made Thai", "Hapa's Brewing", "Donut Delite", "Brewing",
                           "Wicked Popcorn", "Pho Nam", "Samos Greek Isl", "THE CRUCI WASHINGTON DC", "Love Burn Chicken",
                           "Bar", "Grill", "THE BLACKSMITH REDWOOD CITY CA", "GHIRARDELLI", "GOLDEN CORRAL #2486 LARGO MD",
                           "HOMEROOM TO GO OAKLAND CA", "CURRY LEAF SAN FRANCISCOCA", "CRACKED & BATTERED",
                           "CHARLEYS PHILLY STEAKS 9 ARLINGTON VA", "BIMBOS 365 CLUB SAN FRANCISCOCA",
                           "JOSE A MARTINEZ V CAMPBELL CA", "NEVERIA LOS MOCHIS SAN DIEGO CA",
                           "HEALTH PUB- FASHIO ARLINGTON VA", "HILL PRINCE WASHINGTON DC", "SWAMIS NORTH PARK",
                           "ANDERSEN BAKERY", "MQ HEALTHY FAST FOOD", "STORE\*BENS FAST FOOD", "TST\* RAD RADISH",
                           "CURRY UP NOW REDWOOD CITY", "WOOLY PIG", "WAKE CUP", "LUCHO", "THE SPORTS PAGE INC MOUNTAIN VIEW*",
                           "2OAKLAND ARENA OAKLAND CA", "THE ITALIAN HOMEMA", "LA DOLCE VITA GELATO MILPITAS CA",
                           "SHAKE SHACK SAN MATEO", "ROSE BOWL SPECIAL SAN DIEGO", "SIMPLYCAKE SF SAN MATEO", "ASACKOFPOTATOE",
                           "BEST OF THAI NOODLE SAN FRANCISCOCA", "CHE FICO SAN", "UNUSUAL TIMES EWR NEWARK",
                           "BERT\'S STADIUM SPORTS BA SUNNYVALE", "DOG PATCH SFO T1 SAN FRANCISCOCA",
                           "ROSE BOWL SPECIAL PASADENA CA", "FARMER\'S FRIDGE CHICAGO IL02677R", "DAISO", "GIO GELATO ITALIAN",
                           "SPECIAL POPUP MENLO", "THE EPICUREAN TRAD SAN", "URBAN REMEDY UNION S SAN FRANCISCOCA",
                           "TOMO SUSHI AND TERIYAKI DALY CITY CA", 'B STAR SAN', 'CASCAL RESTAURANT MOUNTAIN VIEWCA',
                           'EB GOLDEN HOUR NIGHT 801-413-7200 CAAPPLE PAY ENDING IN 1455','BOBA GUYS POTRERO SAN FRANCISCOCA0001152921512980421691','ADORABLE BAKERY LL SAN FRANCISCOCA0001152921513049179594','MONARCH BEVERAGE C SAN FRANCISCOCA0002305843018002898080','URBAN KITCHEN BURLINGAME','SANDYS SAN FRANCISCOCA00104288013715099959AA'],
            'coffee': ['dutch bros', 'dunkin', 'starbucks', 'peet', 'caffe', 'SCOTTSDALE Q SCOTTSDALE', 'coffee',
                       'MINTS & HONEY'],
            'work_lunch': ['cavasson'],

            # Bills for transportation
            'ride_share': ['uber', 'lyft', 'razor ride', 'spin mobility', 'Lim\*Ride', "Lim\*Sub"],
            'gas_station': ['shell', 'exxon', 'chevron', 'arco', 'circle k', 'love\'s', 'orca', 'QT', 'FUEL 24 7 WESTBOROUGH',
                            'DIMOND FOOD MART LLC', "Royal Farms", "PETRO*", "A&A GAS BURLINGAME CA", "Speedway", "Valero",
                            'A ONE GAS SAN LORENZO CA'],
            'parking': ['parking', 'showcase mall', 'commutifi', 'meter', "MARINER GARAG OXON HILL MD",
                        "PABC MULTI SPACE 3 BALTIMORE MD", "Parkmobile", "Parkwhiz", "UNION STREET PLAZA GARAG SAN FRANCISCOCA",
                        "IMPARK00270201A SAN FRANCISCOCA00811R"],
            'air_travel': ['american', 'alaska', 'united airlines', 'ALLIANZ TRAVEL INS',
                           "TRAVEL GUARD GROUP INC 877-934-8308 WI", "Delta"],
            'lodging': ['GREEN TORTOISE HOSTEL', 'hilton', 'hostel', 'MOTEL SAKURA GLENDALE CA'],
            'tolls': ['fastrak'],

            # Bills for applications
            'netflix': ['netflix'],
            'spotify': ['spotify'],
            'hulu': ['hulu'],
            'viki': ['viki'],
            'nba_league_pass': ['nba'],
            'hbo': ['hbo'],
            'crunchy_roll': ['crunchy'],
            'blossom': ['blossom'],
            'meal_lime': ['meal lime'],
            'apple_tv': ['apple tv'],
            'grammarly': ['grammarly'],
            'youtube_tv': ['youtube', 'GOOGLE \*YT PRIMETIME'],
            'nvidia': ['nvidia'],
            'pay_wall': ['hearst', 'sportplan'],
            'disney': ['disney'],
            'medium': ['medium'],
            'fubo_tv': ['fubotv'],
            'breaking_points': ['KRYSTAL AND SAAGAR'],
            'coursera': ['COURSRA'],
            'onepass': ['onepass'],
            'chatgpt': ['chatgpt'],
            'paramount_plus': ['paramount'],
            'obsidian': ['obsidian'],

            # Bills for Quick purchases
            'conv_store': ['walgreens', 'cvs', '7-eleven', 'BEVERAGES & MORE'],
            'everything_store': ['amazon', 'walmart', 'target', 'staples', 'FIVE BELOW', 'BED BATH'],
            'airport': ['dca', 'faber news', 'vending', 'SKYLINE NEWS AND GIFTS', 'URBAN MKT CONCOURSE D SEATTLE WA'],

            # Bills for fun
            'oculus': ['oculus', 'widmo', 'gauss labs'],
            'onlyfans': ['onlyfans', 'ccbill'],
            'concerts': ['corinne', 'the van buren', 'fleet', 'phoenix performing', 'moore theater', 'ritt Momney',
                         'AKCHIN PAVILION AMPHI PHOENIX AZ', "GREAT AMERICAN MUS", 'see tickets', 'jacob collier', "MIDWAY",
                         "FILLMORE", "UNKNOWN MORTAL ORC", "JAWNYWALLICE", 'THE GREEK THEATER SAN','BENNYSINGSDANA 800-965-4827'],
            'music_festival': ['frontgate', 'festival', 'innings', 'OUTSIDELAND MERCH'],
            'comedy': ['stand up'],
            'live_nba': ['suns', 'sacaramentokings', 'unlv web', 'QUINTEVENTS', 'golden1', 'ticketmaster', 'bill graham',
                         'AMK CAPITAL ONE ARENA CN WASHINGTON DC', "FUZE TECHNOLOGY"],
            'political_cause': ['planned parent', 'GOFUNDME HOMOSEXUAL WA REDWOOD CITY CA'],
            'zoo': ['zoo'],
            'sport_stuff': ['dicks', 'SPORTSLINE', 'BIG 5 SPORTING GOODS'],
            'movies': ['amc', 'ati', 'theatre', 'fandango', 'cine', 'cinema', "PRIME VIDEO"],
            'live_baseball': ['diamond'],
            'museum': ['chihuly', 'musical instrument', 'botanical', 'grand c', 'space needle', "spy museum",
                       "CALIFORNIA ACAD SCIENCES SAN FRANCISCOCA", "CA ACAD. OF SCIENCES O SAN FRANCISCOCATXNREF12345",'SFMOMA MUSEUM STORE SAN FRANCISCOCA00690R'],
            'tennis': ['usta', 'a-z tennis','SAN MATEO PARKS AND RECR 650-522-7408 CA','SLINGERBAG 8554233729 CA','PALO ALTO TENNIS SHOP PALO ALTO CA','TENNIS WAREHOUSE 8008836647 CA'],
            'home': ['casper', "LOWE\'S OF SAN BRUNO, CA SAN BRUNO CA",'SAN MATEO SERVICE FEE 650-522-7408 CA'],
            'parks_rec': ['hoover dam','MUIR SPACE 4288 MILL VALLEY CA'],
            'video_games': ['steam', 'EPIC GAMES', 'Square enix'],
            'live_event': ['showtime', "ESPN PLUS 402-935-7733 CA","PUBLIC WORKS SAN FRANCISCOCA"],
            'vr_arcade': ['r u 4 real', "sandbox vr"],
            'self_care': ['OCEANIC FOOT SPA BURLINGAME', 'stretchlab'],
            'electronics': ['Best Buy', 'SP DROP.COM', "KEYCHRON.COM", 'CENTRAL COMPUTERS'],
            'bowling': ['712 GARAGE LANES'],
            'convention': ['Katsu Kei', 'Hella Kinketsu', 'SALE PRICE TAXES FORT WASHINGTMD',
                           'NEON CULTURE RIDGELAND MS0002305843017072974051'],
            'kids': ['scramble', "THE CAPITAL WHEEL OXON HILL MD"],
            #Bills for personal items (clothing etc)
            'clothing': ['famous footwear', 'foot locker', 'ross', 'straw and wool', 'rei', 'unlv tmc', 'h&m', 'simply seattle',
                         'gdp\*vimraj', 'bonobos', 'uniqlo', 'mens wearhouse', 'foot', 'runner',
                         "GOODWILL OF SAN FRANCI SAN FRANCISCOCA"],
            'wallet': ['minter goods'],
            'hair_supplies': ['waba hair'],
            'home_supplies': ['home depot', 'OFFICE DEPOT', 'MAIDO STATIONERY'],
            'moving': ['u-haul', 'pod', 'Michaels', 'taskrabbit', 'extra space'],
            'mailing': ['FEDEX', 'USPS', "UPS"],
            'fitness': ['Sports Nutri', 'YOGASIX', "OTF", "02738 PF SAN BRUNO CA SAN BRUNO CA", "Rumble", "F45", "CLUBPILATE*",
                        "SP MANDUKA 3104261495 CAAPPLE PAY ENDING IN 1455", "ONNIT", 'MOVEMENT SANTA CLARA 5413165747 CO'],
            'motor_gear': ['GP SPORTS - CA SAN JOSE CA'],
            'jewelry': ['CLAIRE', 'Etsy*', "Rose Gold*"],
            'sports_gear': ['SPORTS COLLECTIBLES', 'TEAMFANSHOP 855-210-8831 FL', "NH ENTERTAINMENT L OXON HILL MD"],
            # Bills for learning
            'learning': ['datacamp', 'interactive', 'udemy', 'linkedin', 'transcript', '\*play', 'book', 'GA TECH', 'WILEY',
                         'COURSE HERO', 'LEETCODE', "LEANPUB 6049168017 CAN", "GA INST TECH",'QUIZLET.COM 510-495-6550 CAP-08481062'],
            'professional': ['linkedin', 'dataspell', 'Finance Plus', 'HARVARD BUS', 'wework', 'github',
                             "INTERVIEW QUERY 6504513704 CA", "FANTASYMATH.COM 9204509068 WI",'APPY PIE 7039964429 VA','DROPDECK 7372426703 MD'],
            'motor_cycle_license': ['PACIFIC MOTORCYCLE TRAIN LIVERMORE CA', 'CYCLE GEAR', 'SP YN MOTO'],
            # Bills for medical services
            'medical': ['banner', 'BHSM REHABILITATIO', 'CARBON HEALTH'],
            'dental': ['river run', "Dental"],
            'vision': ['H. Chiem O.D.', 'CHIEM', 'PAMF PA ONLINE BILL PAY 877-252-1777 CA', 'OAKLEY B'],
            'physical_therapy': ['Ayurbliss Phys', 'Ayurbliss LLC'],
            # Bills for Europe
            'Pre_Europe_Trip': ["Lonely Planet", "1-800 Contacts", "HOOOYI", "ADIDAS 6531 SAN FRANCI SAN FRANCISCOCA",
                                "THE SPORTS BASEMENT REDW REDWOOD CITY CA", "MINISO GREAT MALL MILPITAS CA",
                                "SP KAYO ANIME CLOT 6463129658 CA", "AAA REDWOOD CITY REDWOOD CITY CA22314",
                                "SP PACSAFE 2067227233 WA", "MY FAVORITE SAN"],
            'Europe_Trip': ["Tiqets Inc", "DENT 036416349688 DEUAPPLE PAY ENDING IN 1455"],
            'Kaiya_Birthday': ['WEST COAST CONFECTION 4252207805 CA', "CRUMBL\* SHIPPING 8014101313 UT"],
            'Julie_Birthday': ['PAW PATCH PASTRIES DALY CITY'],
            'credits': ['AUTOMATIC STATEMENT CREDIT']
        }
        for k, v in mapping.items():
            ytd_data.loc[ytd_data.Description.str.contains('|'.join(v), case=False), 'Short_Desc'] = k
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 15.89), 'Short_Desc'] = 'hbo'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 16.95), 'Short_Desc'] = 'hbo'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 20.12), 'Short_Desc'] = 'hbo'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 6.35), 'Short_Desc'] = 'shiloh'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 13.21), 'Short_Desc'] = 'shiloh'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 10.59), 'Short_Desc'] = 'netflix'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 5.29), 'Short_Desc'] = 'apple_tv'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 7.41), 'Short_Desc'] = 'apple_tv'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 38.14), 'Short_Desc'] = 'babbel'
            ytd_data.loc[(ytd_data.Description.str.contains('apple', case=False)) & (
                    ytd_data.Amount == 14.99), 'Short_Desc'] = 'nba_league_pass'
            ytd_data.loc[(ytd_data.Description.str.contains('apple', case=False)) & (
                    ytd_data.Amount == 3.17), 'Short_Desc'] = 'meal_lime'
            ytd_data.loc[
                (ytd_data.Description.str.contains('apple', case=False)) & (ytd_data.Amount == 31.79), 'Short_Desc'] = 'blossom'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (
                    ytd_data['Amount'] == 553.89), 'Short_Desc'] = 'iphone_14'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (
                    ytd_data['Amount'] == 53.72), 'Short_Desc'] = 'iphone_case'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (
                    ytd_data['Amount'] == 76.31), 'Short_Desc'] = 'the_athletic'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (
                    ytd_data['Amount'] == 37.09), 'Short_Desc'] = 'yahoo_fantasy_plus'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (
                    ytd_data['Amount'] == 9.99), 'Short_Desc'] = 'apple_care'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (ytd_data['Amount'] == 26.49) & (
                    ytd_data.Date == '01/2022'), 'Short_Desc'] = 'anki_mobile'
            ytd_data.loc[ytd_data.Description.str.contains("apple", case=False) & (ytd_data['Amount'] == 26.49) & (
                    ytd_data.Date == '11/2022'), 'Short_Desc'] = 'bumble'
            ytd_data.loc[
                (ytd_data.Description.str.contains('venmo', case=False)) & (ytd_data.Amount == 74.68), 'Short_Desc'] = 'adity'
            ytd_data.loc[(ytd_data.Description.str.contains('venmo', case=False)) & (
                    ytd_data.Amount == 88.39), 'Short_Desc'] = 'nick&julie'

    def flag_reoccurring(self):
        reocurring_list = ['breaking_points', 'spotify', 'netflix', 'hulu', 'viki', 'nba_league_pass', 'hbo', 'crunchy_roll',
                           'blossom', 'meal_lime', 'apple_tv', 'grammarly', 'youtube_tv', 'nvidia', 'pay_wall', 'disney',
                           'medium', 'fubo_tv', 'nvidia', 'stretch_zone', 'political_cause', 'state_farm', 'cell_phone', 'gym',
                           'stretch_zone', 'youtube', 'coursera', 'the_athletic', "onepass", "chatgpt", "paramount_plus",
                           'babbel', 'obsidian', 'physical_therapy', 'apple_care']
        ytd_data.loc[ytd_data.Short_Desc.isin(reocurring_list), 'Reoccurring_Flag'] = 'Yes'
        ytd_data.loc[~ytd_data.Short_Desc.isin(reocurring_list), 'Reoccurring_Flag'] = 'No'

        mapping = {
            'Housing': ['home', 'home_supplies', 'lodging'],
            'Transportation': ['ride_share', 'gas_station', 'parking', 'air_travel', 'airport', 'bus_fare', 'tolls',
                               "motor_cycle_license"],
            'Food': ['fast_food', 'restaurant', 'groceries', 'coffee', 'work_lunch'],
            'Insurance': ['state_farm'],
            'Utilities': ['cell_phone', 'aps', 'car', 'storage'],
            'Medical': ['medical', 'dental', "vision", "physical_therapy"],
            'Government': ['taxes'],
            'Savings': [],
            'Personal_Spending': ['anki_mobile', 'conv_store', 'clothing', 'coursera', 'learning', 'staples', 'target',
                                  'stretch_zone', 'bookstore', 'professional', 'political_cause', 'gym', "onepass",
                                  'barbershop', 'wallet', 'everything_store', 'walmart', 'clothes', 'hair_supplies',
                                  'bed_bath_and_beyond', 'amazon', 'five_below', 'big_5_sporting_goods', 'leet_code',
                                  'sports_line', 'iphone_14', 'iphone_case', 'apple_care', "sports_gear", "chatgpt", "fitness",
                                  "jewelry", "motor_gear", 'obsidian', 'self_care'],
            'Recreation_Entertainment': ['babbel', 'breaking_points', 'spotify', 'netflix', 'hulu', 'viki', 'nba_league_pass',
                                         'hbo', 'crunchy_roll', 'blossom', 'meal_lime', 'apple_tv', 'grammarly', 'youtube_tv',
                                         'nvidia', 'pay_wall', 'disney', 'medium', 'fubo_tv', 'onlyfans', 'oculus', 'concert',
                                         'movies', 'museum', 'music_festival', 'live_nba', 'nvidia', 'comedy', 'live_baseball',
                                         'concerts', 'parks_rec', 'tennis', 'vr_arcade', 'video_games', 'live_event',
                                         'sport_stuff', 'zoo', 'electronics', 'bowling', 'youtube', 'the_athletic',
                                         'yahoo_fantasy_plus', 'bumble', "paramount_plus", "convention", 'Pre_Europe_Trip',
                                         "Europe_Trip"],
            'Misc': ['unsure', 'vending', 'moving', 'mailing', 'dump'],
            'People': ['tahjei', 'don', 'dad', 'jayelin', "shiloh", "kids", 'Kaiya_Birthday', 'adity', 'nick&julie','Julie_Birthday'],
            'Payment_and_Interest': ['payment', 'interest', 'cashback_bonus','credits']
        }

        for k, v in mapping.items():
            ytd_data.loc[ytd_data.Short_Desc.isin(v), 'Category_2'] = k

    def run(self):
        self.format_date()
        self.map_transactions()
        self.flag_reoccurring()

if __name__ == "__main__":
    analyzer = BudgetAnalyzer('D:\Sean\Documents\Personal\Budget\YTD_downloads\Discover-2023-YearToDateSummary.csv')
    analyzer.run()
