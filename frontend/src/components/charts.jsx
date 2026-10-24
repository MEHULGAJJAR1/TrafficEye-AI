import React from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3, PieChart as PieIcon } from 'lucide-react';
import { Empty } from './ui';
import { number, percent } from '../utils';

const COLORS = ['#3dd6b0', '#6c9fff', '#b18df1', '#efb864'];
const axis = { fill: '#7c889a', fontSize: 11, fontFamily: 'inherit' };
const grid = { stroke: '#27313f', strokeDasharray: '3 5', vertical: false };
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><strong>{label}</strong>{payload.map(p => <div key={p.name}><i style={{ background: p.color || p.fill }}/><span>{p.name}</span><b>{number(p.value)}</b></div>)}</div>;
}
export function FlowChart({ data, height = 210, violationsOnly = false }) {
  if (!data?.length) return <Empty small icon={BarChart3} title="Your traffic story starts here" text="Process a video to see real counts and confirmed events over time."/>;
  return <div className="chart-frame" style={{ height }}><ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <AreaChart data={data} margin={{ top: 14, right: 8, bottom: 0, left: -25 }}><defs><linearGradient id={violationsOnly ? 'violationsFill' : 'trafficFill'} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={violationsOnly ? '#f2a75b' : '#3dd6b0'} stopOpacity={.28}/><stop offset="100%" stopColor={violationsOnly ? '#f2a75b' : '#3dd6b0'} stopOpacity={0}/></linearGradient></defs><CartesianGrid {...grid}/><XAxis dataKey="label" tick={axis} axisLine={false} tickLine={false} minTickGap={28} dy={9}/><YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false}/><Tooltip content={<ChartTooltip/>}/>{!violationsOnly && <Area type="monotone" dataKey="vehicles" name="New unique vehicles" stroke="#3dd6b0" strokeWidth={2.2} fill="url(#trafficFill)" activeDot={{ r: 5, strokeWidth: 3, stroke: '#173b35' }}/>}<Area type="monotone" dataKey="violations" name="Confirmed violations" stroke="#f2a75b" strokeWidth={1.8} fill={violationsOnly ? 'url(#violationsFill)' : 'transparent'} activeDot={{ r: 4 }}/></AreaChart>
  </ResponsiveContainer></div>;
}
export function Distribution({ data }) {
  const total = data?.reduce((n, d) => n + d.value, 0) || 0;
  if (!total) return <Empty small icon={PieIcon} title="No tracked vehicles yet" text="Class shares use unique tracked vehicles, not repeated box detections."/>;
  return <div className="distribution"><div className="donut"><ResponsiveContainer width="100%" height={178} minWidth={0}><PieChart><Pie data={data} innerRadius={59} outerRadius={77} paddingAngle={4} dataKey="value" stroke="none" startAngle={90} endAngle={-270}>{data.map((d, i) => <Cell key={d.name} fill={COLORS[i]}/>)}</Pie><Tooltip content={<ChartTooltip/>}/></PieChart></ResponsiveContainer><div className="donut-center"><strong>{number(total)}</strong><span>unique vehicles</span></div></div><div className="distribution-legend">{data.map((d, i) => <div key={d.name}><i style={{ background: COLORS[i] }}/><span>{d.name === 'Bike' ? 'Motorcycles' : `${d.name}s`}</span><b>{number(d.value)}</b><small>{percent(100 * d.value / total)}</small></div>)}</div></div>;
}
export function SafetyChart({ data }) {
  if (!data?.length) return <Empty small title="No safety events in this scope" text="Only multi-frame-confirmed records contribute to this chart." icon={BarChart3}/>;
  return <div className="chart-frame" style={{ height: 245 }}><ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={data} margin={{ left: -25, right: 8, top: 12, bottom: 4 }}><CartesianGrid {...grid}/><XAxis dataKey="label" tick={axis} axisLine={false} tickLine={false}/><YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false}/><Tooltip content={<ChartTooltip/>}/><Bar dataKey="helmet" name="No helmet" fill="#efb864" radius={[3, 3, 0, 0]} maxBarSize={22}/><Bar dataKey="seatbelt" name="No seatbelt" fill="#ad91e8" radius={[3, 3, 0, 0]} maxBarSize={22}/></BarChart></ResponsiveContainer></div>;
}
export function DetectionChart({ data }) {
  if (!data?.length) return <Empty small title="No observations yet" text="This chart counts class-labelled box observations in sampled frames." icon={BarChart3}/>;
  return <div className="chart-frame" style={{ height: 268 }}><ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={data} layout="vertical" margin={{ left: 8, right: 20, top: 8, bottom: 0 }}><CartesianGrid stroke="#27313f" horizontal={false}/><XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false}/><YAxis type="category" dataKey="name" width={100} tick={axis} axisLine={false} tickLine={false}/><Tooltip content={<ChartTooltip/>}/><Bar dataKey="value" name="Box observations" fill="#6c9fff" radius={[0, 4, 4, 0]} maxBarSize={15}/></BarChart></ResponsiveContainer></div>;
}
