"""真实五档快照的适配、分块回放及受回调时间约束的分钟历史。"""

from runtime.database.compile import DolphinDBFunction

from .run_backtest import CREATE_BACKTEST_ENGINE


READ_STOCK_SNAPSHOTS = DolphinDBFunction(
    module="backtest",
    definition="""
    def read_stock_snapshots(source, day, codes, begin_time, end_time, history=false) {
        shCodes = symbol(strReplace(string(codes[endsWith(string(codes), ".XSHG")]), ".XSHG", ""))
        szCodes = symbol(strReplace(string(codes[endsWith(string(codes), ".XSHE")]), ".XSHE", ""))
        if (history) {
            return select Market, SecurityID, TradeDate, TradeTime, LastPrice, TotalVolume, TotalAmount
            from source where TradeDate=day, TradeTime>=begin_time, TradeTime<end_time,
                ((Market="SH" && SecurityID in shCodes) || (Market="SZ" && SecurityID in szCodes))
            order by TradeTime, Market, SecurityID
        }
        return select * from source where TradeDate=day, TradeTime>=begin_time, TradeTime<end_time,
            ((Market="SH" && SecurityID in shCodes) || (Market="SZ" && SecurityID in szCodes))
        order by TradeTime, Market, SecurityID
    }
    """,
)


BUILD_STOCK_SNAPSHOT_MESSAGE = DolphinDBFunction(
    module="backtest",
    definition="""
    def build_stock_snapshot_message(raw, reference) {
        valid = select * from raw where isValid(LastPrice), !isNanInf(LastPrice,true), LastPrice>0
        n = valid.rows()
        if (n==0) return table(1:0,
            `symbol`symbolSource`timestamp`lastPrice`upLimitPrice`downLimitPrice`totalBidQty`totalOfferQty`bidPrice`bidQty`offerPrice`offerQty`prevClosePrice,
            [SYMBOL,SYMBOL,TIMESTAMP,DOUBLE,DOUBLE,DOUBLE,LONG,LONG,DOUBLE[],LONG[],DOUBLE[],LONG[],DOUBLE])
        code = symbol(string(valid.SecurityID) + iif(valid.Market=="SH", ".XSHG", ".XSHE"))
        quotes = table(code as code, valid.TradeDate as day,
            timestamp(valid.TradeDate)+long(valid.TradeTime) as timestamp, double(valid.LastPrice) as lastPrice)
        daily = select code, date(time) as day, pre_close, up_limit, down_limit from reference
        quotes = lj(quotes, daily, `code`day)
        for (field in `pre_close`up_limit`down_limit) {
            invalid = isNull(quotes[field]) || isNanInf(double(quotes[field]),true) || quotes[field]<=0
            if (any(invalid)) {
                row = find(invalid, true)
                throw "真实快照缺少有效参考价格：" + string(quotes.code[row]) + " " + string(quotes.day[row]) + " " + string(field)
            }
        }
        // flatten(matrix) 按列展开，转置后每只证券连续存放五档。
        bidMatrix = matrix(valid.BidPrice1, valid.BidPrice2, valid.BidPrice3, valid.BidPrice4, valid.BidPrice5)
        bidQtyMatrix = matrix(valid.BidVolume1, valid.BidVolume2, valid.BidVolume3, valid.BidVolume4, valid.BidVolume5)
        offerMatrix = matrix(valid.AskPrice1, valid.AskPrice2, valid.AskPrice3, valid.AskPrice4, valid.AskPrice5)
        offerQtyMatrix = matrix(valid.AskVolume1, valid.AskVolume2, valid.AskVolume3, valid.AskVolume4, valid.AskVolume5)
        bidPrices = double(flatten(transpose(bidMatrix)))
        bidQuantities = long(flatten(transpose(bidQtyMatrix)))
        offerPrices = double(flatten(transpose(offerMatrix)))
        offerQuantities = long(flatten(transpose(offerQtyMatrix)))
        bidValid = isValid(bidPrices) && !isNanInf(bidPrices,true) && bidPrices>0 && isValid(bidQuantities) && bidQuantities>0
        offerValid = isValid(offerPrices) && !isNanInf(offerPrices,true) && offerPrices>0 && isValid(offerQuantities) && offerQuantities>0
        ends = int(1..n)*5
        return table(quotes.code as symbol,
            symbol(iif(endsWith(string(quotes.code), ".XSHG"), "XSHG", "XSHE")) as symbolSource,
            quotes.timestamp as timestamp, quotes.lastPrice as lastPrice,
            double(quotes.up_limit) as upLimitPrice, double(quotes.down_limit) as downLimitPrice,
            take(0l,n) as totalBidQty, take(0l,n) as totalOfferQty,
            arrayVector(ends,iif(bidValid,bidPrices,0.0)) as bidPrice,
            arrayVector(ends,iif(bidValid,bidQuantities,0l)) as bidQty,
            arrayVector(ends,iif(offerValid,offerPrices,0.0)) as offerPrice,
            arrayVector(ends,iif(offerValid,offerQuantities,0l)) as offerQty,
            double(quotes.pre_close) as prevClosePrice)
    }
    """,
)


BUILD_MINUTE_BARS = DolphinDBFunction(
    module="backtest",
    definition="""
    def build_minute_bars(raw) {
        ordered = select symbol(string(SecurityID)+iif(Market=="SH", ".XSHG", ".XSHE")) as code,
            TradeDate, TradeTime, LastPrice, TotalVolume, TotalAmount
            from raw order by code, TradeDate, TradeTime
        // 首条累计数作为基线；不能把此前未知的成交全算到第一根分钟线。
        update ordered set volume=long(nullFill(deltas(TotalVolume),0)), amount=double(nullFill(deltas(TotalAmount),0)) context by code, TradeDate
        if (any(ordered.volume<0) || any(ordered.amount < -0.000001)) {
            throw "快照累计成交量或成交额在同一交易日内倒退"
        }
        inSession = select * from ordered where
            ((TradeTime>=09:30:00.000 && TradeTime<=11:30:00.000) || (TradeTime>=13:00:00.000 && TradeTime<=15:00:00.000))
        ends = long(ceil(double(long(inSession.TradeTime))/60000.0))*60000
        ends = iif(inSession.TradeTime==09:30:00.000 || inSession.TradeTime==13:00:00.000, ends+60000, ends)
        update inSession set time=timestamp(TradeDate)+ends
        // 无效 LastPrice 不产生 OHLC，但不能因此丢掉该记录的累计成交增量。
        totals = select sum(volume) as volume, sum(amount) as amount from inSession group by time,code
        prices = select first(LastPrice) as open, max(LastPrice) as high, min(LastPrice) as low,
            last(LastPrice) as close from inSession
            where LastPrice>0, isValid(LastPrice), !isNanInf(LastPrice,true) group by time,code
        bars = lj(prices,totals,`time`code)
        return select time,code,open,high,low,close,volume,amount from bars order by time,code
    }
    """,
)


GET_MINUTE_HISTORY = DolphinDBFunction(
    module="backtest",
    definition="""
    def getMinuteHistory(context, msg, codes, count) {
        if (form(count)!=0 || isNull(count) || count<=0 || long(count)!=count) {
            throw "count 必须为正整数"
        }
        state = objByName("coreBacktestSnapshotState")
        if (!state["enabled"]) throw "getMinuteHistory 仅适用于真实快照模式"
        requested = symbol(distinct(string(codes)))
        if (size(requested)==0 || any(!(requested in state["codes"]))) {
            throw "codes 必须是当前回测股票范围内的非空 XSHG/XSHE 代码"
        }
        requested.sort!()
        now = msg.timestamp[0]
        day = date(now)
        cutoff = timestamp(day)+long(floor(double(long(time(now)))/60000.0))*60000
        empty = table(1:0,`time`code`open`high`low`close`volume`amount,[TIMESTAMP,SYMBOL,DOUBLE,DOUBLE,DOUBLE,DOUBLE,LONG,DOUBLE])
        result = empty
        cache = state["history"]
        days = state["historyDates"]
        days = reverse(days[days<=day])
        usedKeys = array(STRING,0)
        for (historyDay in days) {
            // 当日只查询已经结束的分钟，避免预计算未来数据及未来数据错误干扰过去回调。
            boundary = iif(historyDay==day, time(cutoff)+1, 23:59:59.999)
            // 开盘整点属于下一根分钟线，暂不读取，保留此前记录作为差分基线。
            if (historyDay==day && (time(cutoff)==09:30:00.000 || time(cutoff)==13:00:00.000)) {
                boundary = time(cutoff)
            }
            key = string(historyDay)
            usedKeys.append!(key)
            if (key in cache) {
                dayCache = cache[key]
            } else {
                dayCache = dict(SYMBOL,ANY)
            }
            begins = array(TIME,0,size(requested))
            for (stockCode in requested) {
                if (stockCode in dayCache) {
                    entry = dayCache[stockCode]
                } else {
                    entry = dict(STRING,ANY)
                    entry["boundary"] = 00:00:00.000
                    entry["bars"] = empty[0:0]
                }
                if (entry["boundary"]>boundary) {
                    // 回看较早消息时只重置该证券，不影响其他证券的读取进度。
                    entry["boundary"] = 00:00:00.000
                    entry["bars"] = empty[0:0]
                    entry.erase!("previous")
                }
                begins.append!(entry["boundary"])
                dayCache[stockCode] = entry
            }
            // 每只证券维护自己的游标；游标相同的证券仍一次批量查询。
            for (begin in distinct(begins[begins<boundary])) {
                batchCodes = requested[begins==begin]
                raw = read_stock_snapshots(state["source"],historyDay,batchCodes,begin,boundary,true)
                for (stockCode in batchCodes) {
                    entry = dayCache[stockCode]
                    if ("previous" in entry) raw.append!(entry["previous"])
                }
                added = build_minute_bars(raw)
                // previous 只提供差分基线，不重复追加它所属的旧分钟。
                lower = timestamp(historyDay)+long(begin)
                added = select * from added where time>=lower, time<timestamp(historyDay)+long(boundary)
                previous = select top 1 * from raw context by Market,SecurityID csort TradeTime desc
                for (stockCode in batchCodes) {
                    entry = dayCache[stockCode]
                    bars = entry["bars"]
                    bars.append!(select * from added where code=stockCode)
                    entry["bars"] = bars
                    entry["previous"] = select * from previous where
                        symbol(string(SecurityID)+iif(Market=="SH",".XSHG",".XSHE"))=stockCode
                    entry["boundary"] = boundary
                    dayCache[stockCode] = entry
                }
            }
            cache[key] = dayCache
            for (stockCode in requested) {
                entry = dayCache[stockCode]
                bars = entry["bars"]
                result.append!(select * from bars where time<=cutoff)
            }
            counts = select size(time) as n from result group by code
            if (counts.rows()==size(requested) && all(counts.n>=count)) break
        }
        for (key in keys(cache)) {
            if (!(key in usedKeys)) {
                dayCache = cache[key]
                // 只回收本次请求不再需要的旧日，保留其他证券的历史窗口。
                erase!(dayCache,requested)
                if (size(keys(dayCache))==0) {
                    cache.erase!(key)
                } else {
                    cache[key] = dayCache
                }
            }
        }
        state["history"] = cache
        if ("peakHistoryBytes" in state) {
            cacheBytes = 0l
            for (key in keys(cache)) {
                dayCache = cache[key]
                for (stockCode in keys(dayCache)) {
                    entry = dayCache[stockCode]
                    cacheBytes += memSize(entry["bars"])
                    if ("previous" in entry) cacheBytes += memSize(entry["previous"])
                }
            }
            state["peakHistoryBytes"] = max([state["peakHistoryBytes"],cacheBytes])
        }
        ordered = select * from result order by code, time desc
        update ordered set ordinal=cumcount(time) context by code
        return select time,code,open,high,low,close,volume,amount from ordered where ordinal<=count order by time,code
    }
    """,
    dependencies=(READ_STOCK_SNAPSHOTS, BUILD_MINUTE_BARS),
)


SNAPSHOT_CALLBACK = DolphinDBFunction(
    module="backtest",
    definition="""
    def snapshot_callback(mutable context, msg, indicator, callback) {
        state = objByName("coreBacktestSnapshotState")
        day = date(msg.timestamp[0])
        quotes = state["quotes"]
        if (isNull(state["quoteDate"]) || state["quoteDate"]!=day) {
            erase!(quotes,keys(quotes))
            state["quoteDate"] = day
        }
        for (index in 0:msg.rows()) {
            code = msg.symbol[index]
            if (code in state["codes"]) {
                quotes[code] = [msg.timestamp[index],msg.lastPrice[index],msg.bidPrice[0][index],msg.offerPrice[0][index],msg.bidQty[0][index],msg.offerQty[0][index]]
            }
        }
        state["quotes"] = quotes
        callback(context,msg,indicator)
    }
    """,
)


RUN_SNAPSHOT_BACKTEST = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_snapshot_backtest(name, mutable config, source, reference, codes, days, benchmark_message, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback, chunk_minutes=5) {
        if (size(days)==0) throw "真实快照回测区间没有交易日"
        if (chunk_minutes<=0 || chunk_minutes>1440 || int(chunk_minutes)!=chunk_minutes) throw "回放块必须为 1 至 1440 个整分钟"
        state = objByName("coreBacktestSnapshotState")
        state["enabled"] = false
        // 只聚合每天的覆盖与时间边界，不加载整段原始快照。缺失日期必须在
        // 创建引擎、执行任意用户回调前一次性报出，回放时复用这些边界。
        shCodes = symbol(strReplace(string(codes[endsWith(string(codes), ".XSHG")]), ".XSHG", ""))
        szCodes = symbol(strReplace(string(codes[endsWith(string(codes), ".XSHE")]), ".XSHE", ""))
        coverage = select min(TradeTime) as firstTime,max(TradeTime) as lastTime,
            sum(isValid(LastPrice) && !isNanInf(LastPrice,true) && LastPrice>0) as validRows
            from source where TradeDate in days,
                ((Market="SH" && SecurityID in shCodes) || (Market="SZ" && SecurityID in szCodes))
            group by TradeDate
        missingDays = days[!(days in coverage.TradeDate)]
        invalidDays = exec TradeDate from coverage where validRows=0 order by TradeDate
        problems = array(STRING,0)
        if (size(missingDays)>0) problems.append!("真实快照缺少交易日行情："+concat(string(missingDays),", "))
        if (size(invalidDays)>0) problems.append!("真实快照缺少有效交易日行情："+concat(string(invalidDays),", "))
        if (size(problems)>0) throw concat(problems,"；")
        state["enabled"] = true
        state["source"] = source
        state["codes"] = symbol(codes)
        state["quoteDate"] = date()
        state["quotes"] = dict(SYMBOL,ANY)
        state["history"] = dict(STRING,ANY)
        state["peakHistoryBytes"] = 0l
        diagnostics = table(1:0,`day`raw_rows`quote_rows`load_ms`replay_ms`peak_block_bytes`peak_history_bytes,[DATE,LONG,LONG,LONG,LONG,LONG,LONG])
        state["diagnostics"] = diagnostics
        state["historyDates"] = sort(distinct(date(reference.time)))
        wrapped = snapshot_callback{,,,on_snapshot_callback}
        engine = create_backtest_engine(name,config,initialize_callback,before_trading_callback,on_bar_callback,
            wrapped,on_order_callback,on_trade_callback,after_trading_callback,finalize_callback)
        try {
            for (day in days) {
                started = now()
                rawCount = 0l
                quoteCount = 0l
                loadMs = 0l
                replayMs = 0l
                peakBlockBytes = 0l
                state["peakHistoryBytes"] = 0l
                dayReference = select code,time,pre_close,up_limit,down_limit from reference where date(time)=day
                bounds = select firstTime,lastTime from coverage where TradeDate=day
                benchmarkDay = select * from benchmark_message where date(timestamp)=day
                firstMs = long(bounds.firstTime[0])
                lastMs = long(bounds.lastTime[0])
                if (benchmarkDay.rows()>0) {
                    firstMs = min([firstMs,long(min(time(benchmarkDay.timestamp)))])
                    lastMs = max([lastMs,long(max(time(benchmarkDay.timestamp)))])
                }
                blockMs = long(chunk_minutes)*60000
                firstBlock = long(floor(double(firstMs)/blockMs))
                lastBlock = long(floor(double(lastMs)/blockMs))
                for (block in firstBlock..lastBlock) {
                    fromMs = block*blockMs
                    toMs = min([fromMs+long(chunk_minutes)*60000,86399999l])
                    loadedAt = now()
                    raw = read_stock_snapshots(source,day,codes,time(fromMs),time(toMs))
                    loadMs += long(now()-loadedAt)
                    rawCount += raw.rows()
                    if (raw.rows()>0) {
                        message = build_stock_snapshot_message(raw,dayReference)
                    } else {
                        message = benchmark_message[0:0]
                    }
                    quoteCount += message.rows()
                    benchmark = select * from benchmarkDay where time(timestamp)>=time(fromMs),time(timestamp)<time(toMs)
                    if (benchmark.rows()>0) message = unionAll(message,benchmark)
                    if (message.rows()>0) {
                        message.sortBy!(`timestamp`symbol)
                        peakBlockBytes = max([peakBlockBytes,memSize(raw)+memSize(message)])
                        replayAt = now()
                        Backtest::appendQuotationMsg(engine,message)
                        replayMs += long(now()-replayAt)
                        lastMessage = message[(message.rows()-1):message.rows()]
                    }
                }
                print("真实快照 "+string(day)+"：读取 "+string(rawCount)+" 条，回放 "+string(quoteCount)+" 条，剔除无效价格 "+string(rawCount-quoteCount)+" 条，耗时 "+string(now()-started)+"ms")
                diagnostics.append!(table(day as day,rawCount as raw_rows,quoteCount as quote_rows,loadMs as load_ms,replayMs as replay_ms,peakBlockBytes as peak_block_bytes,state["peakHistoryBytes"] as peak_history_bytes))
                state["diagnostics"] = diagnostics
                print("按日性能：加载 "+string(loadMs)+"ms，回放 "+string(replayMs)+"ms，原始/适配块峰值 "+string(peakBlockBytes)+"B，分钟缓存峰值 "+string(state["peakHistoryBytes"])+"B")
                if (quoteCount==0) throw "真实快照缺少有效交易日行情："+string(day)+"；不会自动缩短请求区间"
            }
            update lastMessage set symbol="END",timestamp=timestamp+1
            Backtest::appendQuotationMsg(engine,lastMessage)
        } catch (error) {
            Backtest::dropBacktestEngine(engine)
            state["enabled"] = false
            throw error
        }
        return engine
    }
    """,
    dependencies=(CREATE_BACKTEST_ENGINE, READ_STOCK_SNAPSHOTS, BUILD_STOCK_SNAPSHOT_MESSAGE, SNAPSHOT_CALLBACK),
)
