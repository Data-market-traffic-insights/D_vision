"""예측 전에 사용자가 읽을 수 있는 상권 변화와 전망의 근거를 제시한다."""
import pandas as pd
import plotly.express as px
import streamlit as st
from tram_outlook import industry_outlook, station_outlook, describe_industry
from tram_forecast import forecast_series


def outlook_sections(history, available, demand, sid, radius, industry, year):
    stats = industry_outlook(history,sid,radius,year)
    selected = stats.loc[stats.industry == industry].iloc[0]
    subset = history.loc[(history.station_id==sid)&(history.radius_m==radius)]
    totals = subset.groupby('date').shop_count.sum().sort_index()
    a,b,c = st.columns(3)
    a.metric('주변 전체 등록 상가',f'{int(totals.iloc[-1]):,}개',f"2023년 대비 {int(totals.iloc[-1]-totals.iloc[0]):+,}개",delta_color='off')
    b.metric(f'{industry} 등록 점포',f'{int(selected.latest_count):,}개',f'2023년 대비 {int(selected.count_change):+,}개',delta_color='off')
    c.metric('주변 상가 중 선택 업종',f'{selected.mix_share_pct:.1f}%',f'2023년 대비 {selected.mix_change_pp:+.1f}%p',delta_color='off')
    st.subheader('이 주변 상권에서 읽을 수 있는 변화')
    st.write(describe_industry(selected))
    recent_word = '늘었습니다' if selected.recent_change>0 else '줄었습니다'
    st.write(f'가장 최근 구간인 2025년 10월→2026년 9월에는 {industry} 점포가 {abs(int(selected.recent_change)):,}개 {recent_word}.' if selected.recent_change else '가장 최근 구간인 2025년 10월→2026년 9월에는 선택 업종 점포 수가 같았습니다.')
    st.caption('아래의 증감은 원본에 등록된 점포의 변화입니다. 상가 매출·고객 수·공사 또는 트램의 효과를 측정한 값은 아닙니다.')
    changes, forecast, compare = st.tabs(['어떤 업종이 바뀌었나','앞으로의 변화 비교','다른 정거장과 비교'])
    with changes:
        ordered=stats.sort_values('count_change')
        chart=px.bar(ordered,x='count_change',y='industry',orientation='h',
                     color='collection_break',color_discrete_map={False:'#127C80',True:'#C58C32'},
                     labels={'count_change':'2023→2026 등록 점포 증감(개)','industry':'업종','collection_break':'수집 범위 확인 필요'})
        chart.update_layout(showlegend=False,height=360,margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(chart,key='outlook_changes',config={'displaylogo':False})
        st.caption('황토색: 교육·보건의료. 해당 업종은 시 전체 집계가 급변해 실제 성장으로 단정하기 어렵습니다.')
        view=stats[['industry','first_count','latest_count','count_change','local_change_pct','city_change_pct','relative_change_pct','mix_change_pp']].rename(columns={
            'industry':'업종','first_count':'2023 점포','latest_count':'2026 점포','count_change':'증감(개)',
            'local_change_pct':'주변 변화율(%)','city_change_pct':'대전 동일 업종 변화율(%)',
            'relative_change_pct':'대전 대비 비중 변화율(%)','mix_change_pp':'주변 업종 구성 변화(%p)'})
        st.dataframe(view,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(format='%.1f') for c in view.columns if '%' in c})
        st.caption('대전 대비 비중 변화율은 (2026 주변 점포/대전 점포) ÷ (2023 주변 점포/대전 점포) − 1입니다. 업종 구성 변화는 주변 전체 상가 내 비율의 차이입니다. 기준 점포가 0이면 변화율은 비워 둡니다.')
        series=subset.loc[subset.industry==industry].sort_values('date')
        if int(series.shop_count.iloc[0])>0:
            index=pd.DataFrame({'기준일':series.date,'선택 정거장 주변':series.shop_count/series.shop_count.iloc[0]*100,
                                '대전 전체 동일 업종':series.city_count/series.city_count.iloc[0]*100})
            index=index.melt(id_vars='기준일',var_name='범위',value_name='2023년=100')
            st.plotly_chart(px.line(index,x='기준일',y='2023년=100',color='범위',markers=True),key='outlook_city_comparison',config={'displaylogo':False})
    with forecast:
        st.write(f'**{year}년까지 최근 수준이 유지되는 경우와 과거 상대 비중 추세가 이어지는 경우**를 함께 비교합니다.')
        a,b=st.columns(2)
        a.metric('최근 수준 유지 기준',f'{selected.persistence_count:,.1f}개',delta='현재와 같은 값',delta_color='off')
        b.metric('과거 비중 추세가 이어질 경우',f'{selected.trend_count:,.1f}개',delta=f'{selected.trend_delta:+,.1f}개',delta_color='off')
        if abs(selected.trend_delta)<0.05:
            st.write('선택 업종의 상대 비중 추세가 작아 두 계산 결과가 거의 같습니다.')
        else:
            st.write(f"추세가 이어진다는 가정에서는 현재보다 약 {abs(selected.trend_delta):.1f}개 {'많아지는' if selected.trend_delta>0 else '적어지는'} 방향입니다. 트램 수요는 아직 이 값에 더하지 않았습니다.")
        st.write(f'이 정거장·반경·업종의 2026년 검증 오차는 추세 **{selected.trend_error_count:.1f}개**, 유지 기준 **{selected.persistence_error_count:.1f}개**로 환산됩니다. 같은 비중 오차에 2026년 대전 업종 규모를 곱해 비교한 값입니다.')
        st.caption('검증 오차는 단 한 번의 과거 예측에서 나온 절대 차이이며 미래 오차 범위나 신뢰구간이 아닙니다. 모든 점포 수 추정은 대전 전체 동일 업종 규모를 2026년 수준으로 고정한 조건입니다.')
        series=subset.loc[subset.industry==industry].sort_values('date')
        curve=[]
        for y in range(2026,year+1):
            for key,label in [('trend','상대 비중 추세 가정'),('persistence','최근 수준 유지')]:
                count=float(selected.latest_count) if y==2026 else forecast_series(series,f'{y}-09-30',key)['count']
                curve.append({'연도':y,'점포 수(개)':count,'계산 기준':label})
        chart=px.line(pd.DataFrame(curve),x='연도',y='점포 수(개)',color='계산 기준',markers=True)
        chart.update_xaxes(dtick=1,tickformat='d')
        st.plotly_chart(chart,key='outlook_future_comparison',config={'displaylogo':False})
        table=stats[['industry','latest_count','persistence_count','trend_count','trend_delta','collection_break']].rename(columns={
            'industry':'업종','latest_count':'현재 점포','persistence_count':'유지 기준(개)',
            'trend_count':f'{year} 추세 가정(개)','trend_delta':'추세 가정 증감(개)','collection_break':'수집 범위 확인 필요'})
        st.dataframe(table,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(format='%.1f') for c in table.columns if '(개)' in c})
        st.download_button('전체 업종 변화·전망 CSV',view.merge(table,on='업종').to_csv(index=False).encode('utf-8-sig'),f'tram_{sid}_{radius}_{year}_outlook.csv','text/csv')
    with compare:
        comparisons=station_outlook(history,available,demand,radius,industry,year)
        st.write(f'**같은 {radius}m·같은 {industry} 업종**으로 비교합니다. 계획 수요는 정거장 번호로 임시 연결한 값입니다.')
        shown=comparisons[['station_id','station_name','latest_count','count_change','relative_change_pct','trend_count','planned_total','planned_rank']].rename(columns={
            'station_id':'정거장번호','station_name':'정거장','latest_count':'현재 점포','count_change':'2023 대비 증감',
            'relative_change_pct':'대전 대비 비중 변화율(%)','trend_count':f'{year} 추세 가정(개)',
            'planned_total':'2030 계획 승하차 합계','planned_rank':'계획 수요 순위(45곳 중)'})
        st.dataframe(shown,hide_index=True,width='stretch',column_config={
            '대전 대비 비중 변화율(%)':st.column_config.NumberColumn(format='%.1f'),f'{year} 추세 가정(개)':st.column_config.NumberColumn(format='%.1f')})
        planned=comparisons.loc[comparisons.station_id==sid].iloc[0]
        st.write(f"선택 정거장의 계획 승하차 합계는 **{int(planned.planned_total):,}**, 45곳 중 **{int(planned.planned_rank)}위**, 전체 정거장 중앙값의 **{planned.planned_vs_median:.2f}배**입니다.")
        st.caption('계획 수요 순위는 상권 성장성·수익성 순위가 아닙니다. 비교는 승인 좌표 5곳 기준이며, 반경이 겹칠 수 있어 점포 수를 합산하지 않습니다. 계획 수요의 단위·집계기간과 번호 대응은 원표 확인이 필요합니다.')
        st.download_button('정거장 비교 CSV',shown.to_csv(index=False).encode('utf-8-sig'),f'tram_station_comparison_{industry}.csv','text/csv')
    return stats
