import { createBrowserRouter } from 'react-router-dom';
import { App } from '../App';
import { AiResultsPage } from '../pages/AiResultsPage';
import { FocusPage } from '../pages/FocusPage';
import { HistoryPage } from '../pages/HistoryPage';
import { MarketOverviewPage } from '../pages/MarketOverviewPage';
import { StockDetailPage } from '../pages/StockDetailPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <MarketOverviewPage /> },
      { path: 'results', element: <AiResultsPage /> },
      { path: 'stocks/:stockCode', element: <StockDetailPage /> },
      { path: 'focus', element: <FocusPage /> },
      { path: 'history', element: <HistoryPage /> },
    ],
  },
]);
