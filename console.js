(async () => {
  try {
    const FWUID = 'WUdfaXlIZDNDQ0lZLWNFZDMtVGZ3d2tVMjdnTGFERUU2S3FfSVdrcU92bkExNC4xOTIuODM4ODYwOA';
    const APP = '1712_xZHiuQoc1HHcvGz4vs6mGA';
    const BASE = '/areaprivada';
    const token = window.$A && window.$A.d && window.$A.d.Cc;
    if (!token) {
      console.log('Open this on the portal page after login.');
      return;
    }
    const context = () => JSON.stringify({
      mode: 'PROD', fwuid: FWUID, app: 'siteforce:communityApp',
      loaded: { 'APPLICATION@markup://siteforce:communityApp': APP },
      dn: [], globals: {}, uad: true
    });
    async function aura(route, descriptor, calling, params, page) {
      const message = JSON.stringify({
        actions: [{ id: '1;a', descriptor: descriptor, callingDescriptor: calling, params: params }]
      });
      const body = new URLSearchParams({
        message: message, 'aura.context': context(), 'aura.pageURI': page, 'aura.token': token
      }).toString();
      const response = await fetch(BASE + '/s/sfsites/aura?r=1&other.' + route + '=1', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
        body: body
      });
      const payload = JSON.parse(await response.text());
      const action = payload.actions[0];
      if (action.state !== 'SUCCESS') {
        throw new Error(action.error && action.error[0] ? action.error[0].message : action.state);
      }
      return action.returnValue;
    }
    const round = (n) => Math.round(n * 1000) / 1000;

    const answer = prompt(
      'Type one of these:\n  status\n  month 2026-09\n  range 2026-09-01 2026-09-30',
      'month ' + new Date().toISOString().slice(0, 7));
    if (!answer) return;
    const parts = answer.trim().split(/\s+/);

    const info = await aura('WP_Monitor_CTRL.getLoginInfo',
      'apex://WP_Monitor_CTRL/ACTION$getLoginInfo', 'markup://c:WP_Monitor',
      { serviceNumber: '' }, '/areaprivada/s/');
    const vis = info.visibility.Id;
    const cupsResult = await aura('WP_Measure_v3_CTRL.getListCups',
      'apex://WP_Measure_v3_CTRL/ACTION$getListCups', 'markup://c:WP_Measure_List_v4',
      { sIdentificador: vis }, '/areaprivada/s/wp-measurelist-v4');
    const contracts = cupsResult.data.lstContAux;
    let contract = null;
    for (const c of contracts) { if (!c.Version_end_date__c) { contract = c; break; } }
    if (!contract) contract = contracts[0];

    const out = { ok: true, mode: parts[0], cups: contract.CUPs__r.Name, contract_id: contract.Id };

    if (parts[0] === 'status') {
      out.supplies = contracts.map((c) => ({
        contract_id: c.Id, cups: c.CUPs__r.Name,
        start: c.Version_start_date__c, end: c.Version_end_date__c,
        power_kw: c.Requested_power_1__c
      }));
    } else {
      let from, to;
      if (parts[0] === 'month') {
        const ym = parts[1].split('-');
        const last = new Date(+ym[0], +ym[1], 0).getDate();
        from = ym[0] + '-' + ym[1] + '-01';
        to = ym[0] + '-' + ym[1] + '-' + String(last).padStart(2, '0');
      } else {
        from = parts[1];
        to = parts[2];
      }
      const detail = await aura('WP_Measure_v3_CTRL.getInfo',
        'apex://WP_Measure_v3_CTRL/ACTION$getInfo', 'markup://c:WP_Measure_Detail_v4',
        { contId: contract.Id, visId: vis },
        '/areaprivada/s/wp-measure-detail-v4?aId=' + contract.Id + '&vis=' + vis);
      if (detail.minDate && from < detail.minDate) from = detail.minDate;
      if (detail.maxDate && to > detail.maxDate) to = detail.maxDate;

      const data = await aura('WP_Measure_v3_CTRL.getChartPointsByRange',
        'apex://WP_Measure_v3_CTRL/ACTION$getChartPointsByRange',
        'markup://c:WP_Measure_Detail_Filter_By_Dates_v3',
        { contId: contract.Id, type: '4', startDate: from, endDate: to },
        '/areaprivada/s/wp-measure-detail-v4?aId=' + contract.Id + '&vis=' + vis);

      let flat = [];
      (data.lstData || []).forEach((group) => {
        if (Array.isArray(group)) flat = flat.concat(group); else flat.push(group);
      });
      const periods = {}, days = {};
      let total = 0, measured = 0, estimated = 0, mh = 0, eh = 0;
      flat.forEach((row) => {
        const value = row.valueDouble || 0;
        total += value;
        const period = row.tariffPeriod ? 'P' + row.tariffPeriod : null;
        if (period) periods[period] = (periods[period] || 0) + value;
        const day = days[row.date] || (days[row.date] = {
          date: row.date, kwh: 0, periods: {}, measured_hours: 0, estimated_hours: 0
        });
        day.kwh += value;
        if (period) day.periods[period] = (day.periods[period] || 0) + value;
        if (row.obtainingMethod === 'R') { day.measured_hours++; mh++; measured += value; }
        else if (row.obtainingMethod === 'E') { day.estimated_hours++; eh++; estimated += value; }
      });
      const dayList = Object.keys(days).map((k) => days[k]);
      dayList.forEach((day) => {
        day.kwh = round(day.kwh);
        Object.keys(day.periods).forEach((k) => { day.periods[k] = round(day.periods[k]); });
        day.kind = day.estimated_hours && day.measured_hours ? 'mixed'
          : (day.estimated_hours ? 'estimated' : (day.measured_hours ? 'measured' : 'no_data'));
      });
      Object.keys(periods).forEach((k) => { periods[k] = round(periods[k]); });
      out.from = from;
      out.to = to;
      out.total_kwh = round(total);
      out.peak_demand_kw = data.maxPerMonth;
      out.periods_kwh = periods;
      out.measured_kwh = round(measured);
      out.estimated_kwh = round(estimated);
      out.measured_hours = mh;
      out.estimated_hours = eh;
      out.days = dayList;
    }

    const text = JSON.stringify(out);
    copy(text);
    console.log('Done. The result is in your clipboard.');
    console.log('Now run:  python edistribucion.py paste');
    console.log('Paste the result and press Enter, then Ctrl+Z, then Enter.');
    console.log(out);
  } catch (e) {
    console.log('Error: ' + e);
  }
})();
