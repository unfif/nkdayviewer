from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import copy as cp
from settings import env

db = SQLAlchemy()
DATABASE_URL = env.get('DATABASE_URL')
engine = db.create_engine(DATABASE_URL, {})
meta = db.MetaData()
meta.reflect(bind=engine)
table = meta.tables['nkdayraces']
cols = table.c

def init_db(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

class Nkdayraces():
    def getRaces():
        data = {}
        con = engine.connect()
        sql = table.select().order_by(cols.place, cols.racenum, cols.placenum)
        racesdf = pd.read_sql(sql, con)

        racesdf.title = racesdf.title.apply(lambda x: x.rstrip('クラス'))
        racesdf.posttime = racesdf.posttime.apply(lambda x: x.strftime('%H:%M'))
        racesdf.time = racesdf.time.apply(lambda x: x.strftime('%M:%S %f')[1:].rstrip('0') if x is not None else None)

        racesdf = racesdf.sort_values(['place', 'racenum', 'placenum']).reset_index(drop=True)
        racesdf['placenum'] = racesdf[['place', 'racenum', 'placenum']].groupby(['place', 'racenum']).rank(na_option='bottom').astype(int)

        racesdf['nextracerank'] = racesdf.loc[1:, 'placenum'].reset_index(drop=True)
        racesdf.loc[racesdf['placenum'] < 4, 'rankinfo'] = 'initdisp'
        racesdf.loc[(racesdf['placenum'] < 4) & (racesdf['nextracerank'] >= 4), 'rankinfo'] = 'initend'
        racesdf.loc[racesdf['placenum'] >= 4, 'rankinfo'] = 'initnone'
        racesdf.loc[racesdf['nextracerank'] - racesdf['placenum'] < 0, 'rankinfo'] = 'raceend'

        sql = "SELECT psat.relname as TABLE_NAME, pa.attname as COLUMN_NAME, pd.description as COLUMN_COMMENT "
        sql += "FROM pg_stat_all_tables psat, pg_description pd, pg_attribute pa "
        sql += "WHERE psat.schemaname = (select schemaname from pg_stat_user_tables where relname = 'nkdayraces') "
        sql += "and psat.relname = 'nkdayraces' and psat.relid=pd.objoid "
        sql += "and pd.objsubid != 0 and pd.objoid=pa.attrelid and pd.objsubid=pa.attnum "
        sql += "ORDER BY pd.objsubid"

        jplabels = {}
        comments = pd.read_sql(sql, con)
        con.close()

        jockeyct = pd.crosstab([racesdf.place, racesdf.jockey], racesdf.placenum, margins=True)
        jockeyct.columns = [int(x) if type(x) is float else x for x in jockeyct.columns]

        ranges = [list(range(1, x+1)) for x in range(1, 4)]
        jockeyct['単勝率'], jockeyct['連対率'], jockeyct['複勝率'] = [round(100 * jockeyct[range].sum(axis=1) / jockeyct.All, 1) for range in ranges]

        jockeyct = jockeyct[[1,2,3, '単勝率', '連対率', '複勝率', 'All']].sort_values(['place',1,2,3], ascending=False)
        lastplace = ''
        lastindex = ''
        for index in jockeyct.index:
            if index[0] != lastplace:
                jockeyct.at[index, 'dispmode'] = 'place1st'
                jockeyct.at[lastindex, 'dispmode'] = 'placelast'

            lastplace = index[0]
            lastindex = index

        jockeyct = jockeyct.drop(('All', ''))
        jockeyct = jockeyct.rename(columns={1:'1着',2:'2着',3:'3着','All':'騎乗数'})
        jockeysindex = list(jockeyct.columns)
        jockeysindex.remove('騎乗数')
        jockeysindex.insert(0,'騎乗数')
        data['jockeys'] = jockeyct[jockeysindex]

        for comment in comments.loc[:, 'column_name':'column_comment'].iterrows():
            jplabels.update({comment[1].column_name: comment[1].column_comment})

        data['racesdf'] = racesdf.rename(columns=jplabels)

        racesgp = cp.deepcopy(data['racesdf'])
        racesgp['R2'] = racesgp.R
        racesgp[['賞金', '通過']] = racesgp[['賞金', '通過']].applymap(str)
        racesgp = racesgp.query('順位 < 4').groupby(['場所','R','レースID','クラス','形式','距離','天候','状態','情報','日時','日程','時刻','グレード','頭数','賞金'])
        racesgp2 = racesgp.agg(list)
        racesgp2.R2 = racesgp2.R2.apply(set)
        racesgp2 = racesgp2.applymap(lambda x: '(' + ', '.join(map(str, x)) + ')')
        racesgp2 = racesgp2.groupby(['場所','形式']).agg(list).applymap(lambda x: '[' + ', '.join(map(str, x)) + ']')
        racesgp2 = racesgp2.applymap(lambda x: x.strip('['']'))
        racesgp2.R2 = racesgp2.R2.apply(lambda x: x.replace('(', '').replace(')', ''))
        racesgp2['場所形式'] = racesgp2.index
        data['racesgp2'] = racesgp2[['R2','枠番','馬番','人気','騎手','場所形式']].rename(columns={'R2':'R'})

        return data
