import {chromium} from 'playwright';
import {pathToFileURL} from 'node:url';

const frontendBaseUrl = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:5173';

export function getBrowserChannelCandidates(env = process.env) {
    const explicitChannel = env.PLAYWRIGHT_BROWSER_CHANNEL?.trim();
    if (explicitChannel) {
        return [explicitChannel];
    }

    return ['msedge', 'chrome'];
}

async function launchInstalledBrowser() {
    const errors = [];

    for (const channel of getBrowserChannelCandidates()) {
        try {
            return await chromium.launch({channel, headless: true});
        } catch (error) {
            errors.push(`${channel}: ${error.message}`);
        }
    }

    throw new Error(
        [
            '未找到可用的本机 Chromium 浏览器。请安装 Microsoft Edge 或 Google Chrome，',
            '或设置 PLAYWRIGHT_BROWSER_CHANNEL 指定浏览器 channel。',
            `尝试结果：${errors.join(' | ')}`,
        ].join('')
    );
}

function summarizeJson(url, body) {
    if (!body || typeof body !== 'object') {
        return {note: 'non-json-or-empty-body'};
    }

    if (url.includes('/api/market/overview')) {
        return {
            summary_trade_date: body?.summary?.trade_date ?? null,
            stocks_count: Array.isArray(body?.stocks) ? body.stocks.length : null,
            hot_sectors_count: Array.isArray(body?.hot_sectors) ? body.hot_sectors.length : null,
        };
    }

    if (url.endsWith('/api/data-init/overview')) {
        return {
            init_completed: body?.init_completed ?? null,
            market_data_start_date: body?.market_data_start_date ?? null,
            market_data_end_date: body?.market_data_end_date ?? null,
            board_counts_size: body?.board_counts ? Object.keys(body.board_counts).length : null,
        };
    }

    if (url.endsWith('/api/data-init/init/overview')) {
        return {
            running_task_status: body?.running_task?.status ?? null,
            latest_task_status: body?.latest_task?.status ?? null,
            min_trade_date: body?.data_range?.min_trade_date ?? null,
            max_trade_date: body?.data_range?.max_trade_date ?? null,
            trading_day_count: body?.data_range?.trading_day_count ?? null,
        };
    }

    if (/\/api\/market\/stocks\/\d{6}(\?.*)?$/.test(url)) {
        return {
            stock_code: body?.stock_code ?? null,
            trade_date: body?.trade_date ?? null,
            daily_bars_count: Array.isArray(body?.daily_bars) ? body.daily_bars.length : null,
        };
    }

    if (url.includes('/api/market/stocks/') && url.includes('/bars')) {
        return {
            stock_code: body?.stock_code ?? null,
            has_more_before: body?.has_more_before ?? null,
            daily_bars_count: Array.isArray(body?.daily_bars) ? body.daily_bars.length : null,
        };
    }

    return {
        keys: Object.keys(body).slice(0, 8),
    };
}

async function run() {
    const browser = await launchInstalledBrowser();
    const context = await browser.newContext();
    const page = await context.newPage();

    const apiLogs = [];

    page.on('response', async (response) => {
        const url = response.url();
        if (!url.includes('/api/')) {
            return;
        }

        const status = response.status();
        let summary;

        try {
            const body = await response.json();
            summary = summarizeJson(url, body);
        } catch {
            summary = {note: 'response-not-json'};
        }

        apiLogs.push({url, status, summary});
    });

    const steps = [
        '/',
        '/market',
        '/stocks/000001',
        '/initialize',
    ];

    for (const path of steps) {
        await page.goto(`${frontendBaseUrl}${path}`, {waitUntil: 'networkidle', timeout: 30000});
        await page.waitForTimeout(1200);
    }

    await browser.close();

    console.log('PLAYWRIGHT_CHECK_RESULT_START');
    for (const row of apiLogs) {
        console.log(JSON.stringify(row));
    }
    console.log('PLAYWRIGHT_CHECK_RESULT_END');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    run().catch((error) => {
        console.error('PLAYWRIGHT_CHECK_FAILED', error);
        process.exitCode = 1;
    });
}

