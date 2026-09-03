import { ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { DashboardCard } from './ui';
const COLORS = ['#2563EB', '#0D9488', '#D97706', '#DC2626', '#64748B'];

export function ChartCard({ title, data, type = 'bar', dataKey = 'value', nameKey = 'name' }) {
  return <DashboardCard title={title} className="min-h-[280px]"><ResponsiveContainer width="100%" height={220}>{type === 'line' ? <LineChart data={data}><XAxis dataKey={nameKey} /><YAxis /><Tooltip /><Line type="monotone" dataKey={dataKey} stroke="#2563EB" strokeWidth={2} /></LineChart> : type === 'donut' ? <PieChart><Pie data={data} dataKey={dataKey} nameKey={nameKey} innerRadius={55} outerRadius={82}>{data.map((_, i) => <Cell fill={COLORS[i % COLORS.length]} key={i} />)}</Pie><Tooltip /></PieChart> : <BarChart data={data}><XAxis dataKey={nameKey} /><YAxis /><Tooltip /><Bar dataKey={dataKey} fill="#2563EB" radius={[4, 4, 0, 0]} /></BarChart>}</ResponsiveContainer></DashboardCard>;
}
