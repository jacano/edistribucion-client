(function () {
  var FWUID = 'WUdfaXlIZDNDQ0lZLWNFZDMtVGZ3d2tVMjdnTGFERUU2S3FfSVdrcU92bkExNC4xOTIuODM4ODYwOA';
  var APP = '1712_xZHiuQoc1HHcvGz4vs6mGA';
  var BASE = '/areaprivada';

  function token() {
    return window.$A && window.$A.d && window.$A.d.Cc;
  }

  function context() {
    return JSON.stringify({
      mode: 'PROD', fwuid: FWUID, app: 'siteforce:communityApp',
      loaded: { 'APPLICATION@markup://siteforce:communityApp': APP },
      dn: [], globals: {}, uad: true
    });
  }

  async function aura(route, descriptor, calling, params, page) {
    var message = JSON.stringify({
      actions: [{ id: '1;a', descriptor: descriptor, callingDescriptor: calling, params: params }]
    });
    var body = new URLSearchParams({
      message: message, 'aura.context': context(), 'aura.pageURI': page, 'aura.token': token()
    }).toString();
    var response = await fetch(BASE + '/s/sfsites/aura?r=1&other.' + route + '=1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body: body
    });
    var payload = JSON.parse(await response.text());
    var action = payload.actions[0];
    if (action.state !== 'SUCCESS') {
      throw new Error(action.error && action.error[0] ? action.error[0].message : action.state);
    }
    return action.returnValue;
  }

  function round(n) {
    return Math.round(n * 1000) / 1000;
  }

  function lastDay(year, month) {
    return new Date(year, month, 0).getDate();
  }

  function run() {
    if (!token()) {
      alert('Open this on a page of zonaprivada.edistribucion.com after login.');
      return;
    }
    var answer = prompt(
      'Type one of these:\n  status\n  month 2026-09\n  range 2026-09-01 2026-09-30',
      'month ' + new Date().toISOString().slice(0, 7));
    if (!answer) return;
    var parts = answer.trim().split(/\s+/);

    return (async function () {
      try {
        var info = await aura('WP_Monitor_CTRL.getLoginInfo',
          'apex://WP_Monitor_CTRL/ACTION$getLoginInfo', 'markup://c:WP_Monitor',
          { serviceNumber: '' }, '/areaprivada/s/');
        var vis = info.visibility.Id;

        var cupsResult = await aura('WP_Measure_v3_CTRL.getListCups',
          'apex://WP_Measure_v3_CTRL/ACTION$getListCups', 'markup://c:WP_Measure_List_v4',
          { sIdentificador: vis }, '/areaprivada/s/wp-measurelist-v4');
        var contracts = cupsResult.data.lstContAux;

        var contract = null;
        for (var i = 0; i < contracts.length; i++) {
          if (!contracts[i].Version_end_date__c) { contract = contracts[i]; break; }
        }
        if (!contract) contract = contracts[0];

        var out = {
          ok: true, mode: parts[0], cups: contract.CUPs__r.Name, contract_id: contract.Id
        };

        if (parts[0] === 'status') {
          out.supplies = contracts.map(function (c) {
            return {
              contract_id: c.Id, cups: c.CUPs__r.Name,
              start: c.Version_start_date__c, end: c.Version_end_date__c,
              power_kw: c.Requested_power_1__c
            };
          });
        } else {
          var from, to;
          if (parts[0] === 'month') {
            var ym = parts[1].split('-');
            from = ym[0] + '-' + ym[1] + '-01';
            to = ym[0] + '-' + ym[1] + '-' + lastDay(+ym[0], +ym[1]);
          } else {
            from = parts[1];
            to = parts[2];
          }

          var detail = await aura('WP_Measure_v3_CTRL.getInfo',
            'apex://WP_Measure_v3_CTRL/ACTION$getInfo', 'markup://c:WP_Measure_Detail_v4',
            { contId: contract.Id, visId: vis },
            '/areaprivada/s/wp-measure-detail-v4?aId=' + contract.Id + '&vis=' + vis);
          if (detail.minDate && from < detail.minDate) from = detail.minDate;
          if (detail.maxDate && to > detail.maxDate) to = detail.maxDate;

          var data = await aura('WP_Measure_v3_CTRL.getChartPointsByRange',
            'apex://WP_Measure_v3_CTRL/ACTION$getChartPointsByRange',
            'markup://c:WP_Measure_Detail_Filter_By_Dates_v3',
            { contId: contract.Id, type: '4', startDate: from, endDate: to },
            '/areaprivada/s/wp-measure-detail-v4?aId=' + contract.Id + '&vis=' + vis);

          var flat = [];
          (data.lstData || []).forEach(function (group) {
            if (Array.isArray(group)) flat = flat.concat(group); else flat.push(group);
          });

          var periods = {}, days = {}, total = 0, measured = 0, estimated = 0, mh = 0, eh = 0;
          flat.forEach(function (row) {
            var value = row.valueDouble || 0;
            total += value;
            var period = row.tariffPeriod ? 'P' + row.tariffPeriod : null;
            if (period) periods[period] = (periods[period] || 0) + value;
            var day = days[row.date] || (days[row.date] = {
              date: row.date, kwh: 0, periods: {}, measured_hours: 0, estimated_hours: 0
            });
            day.kwh += value;
            if (period) day.periods[period] = (day.periods[period] || 0) + value;
            if (row.obtainingMethod === 'R') { day.measured_hours++; mh++; measured += value; }
            else if (row.obtainingMethod === 'E') { day.estimated_hours++; eh++; estimated += value; }
          });

          var dayList = Object.keys(days).map(function (key) { return days[key]; });
          dayList.forEach(function (day) {
            day.kwh = round(day.kwh);
            Object.keys(day.periods).forEach(function (key) { day.periods[key] = round(day.periods[key]); });
            day.kind = day.estimated_hours && day.measured_hours ? 'mixed'
              : (day.estimated_hours ? 'estimated' : (day.measured_hours ? 'measured' : 'no_data'));
          });
          Object.keys(periods).forEach(function (key) { periods[key] = round(periods[key]); });

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

        var payload = btoa(unescape(encodeURIComponent(JSON.stringify(out))));
        location.href = 'edist://callback?data=' + encodeURIComponent(payload);
      } catch (e) {
        alert('Error: ' + e);
      }
    })();
  }

  run();
})();
