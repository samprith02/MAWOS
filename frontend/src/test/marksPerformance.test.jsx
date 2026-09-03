import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import MarksPerformance, { calculateMarksSummary, mapMarksForPerformance } from '../pages/student/MarksPerformance';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  BarChart: ({ data, children }) => <div data-testid="bar-data">{data.map((row) => `${row.subject}:${row.assessment}:${row.percentage}`).join('|')}{children}</div>,
  Bar: ({ children }) => <div>{children}</div>, Cell: () => null, Legend: () => null,
  ReferenceLine: () => null, Tooltip: () => null, XAxis: () => null, YAxis: () => null,
}));

const marks = [
  { subject: '23AI51', name: 'Machine Learning', internals: { 'CIE-1': 35, 'CIE-2': 20 }, assessment_details: { 'CIE-1': { marks: 35, max_marks: 50 }, 'CIE-2': { marks: 20, max_marks: 40 } } },
  { subject: '23AI52', name: 'Database Management Systems', internals: { 'CIE-1': 20, 'CIE-2': 35 }, assessment_details: { 'CIE-1': { marks: 20, max_marks: 50 }, 'CIE-2': { marks: 35, max_marks: 50 } } },
];

describe('Student Marks Performance', () => {
  it('renders the chart section using API-provided subject marks', () => { render(<MarksPerformance marks={marks} semester={5} />); expect(screen.getByText('Marks Performance')).toBeInTheDocument(); expect(screen.getByTestId('marks-performance-chart')).toBeInTheDocument(); expect(screen.getByTestId('bar-data')).toHaveTextContent('23AI51:CIE average:61.1'); });
  it('maps maximum marks and normalized percentages correctly', () => { expect(mapMarksForPerformance(marks, 'CIE-2')).toEqual(expect.arrayContaining([expect.objectContaining({ subject: '23AI51', obtained: 20, maximum: 40, percentage: 50 }), expect.objectContaining({ subject: '23AI52', percentage: 70 })])); });
  it('changes the assessment filter without a page reload', () => { render(<MarksPerformance marks={marks} semester={5} />); fireEvent.change(screen.getByLabelText('Assessment type'), { target: { value: 'CIE-1' } }); expect(screen.getByTestId('bar-data')).toHaveTextContent('23AI51:CIE-1:70'); expect(screen.getByTestId('bar-data')).not.toHaveTextContent('CIE average'); });
  it('shows an empty state when marks are unavailable', () => { render(<MarksPerformance marks={[]} semester={5} />); expect(screen.getByText('No valid marks available')).toBeInTheDocument(); });
  it('discards invalid API values without crashing', () => { expect(mapMarksForPerformance([{ subject: 'X', internals: { 'CIE-1': 99 }, assessment_details: { 'CIE-1': { marks: 99, max_marks: 50 } } }])).toEqual([]); });
  it('calculates passed, failed, and overall performance summary', () => { expect(calculateMarksSummary([{ subject: 'A', percentage: 80, status: 'Passed' }, { subject: 'B', percentage: 30, status: 'Failed' }])).toMatchObject({ average: 55, highest: { subject: 'A' }, lowest: { subject: 'B' }, passed: 1, failed: 1, status: 'Needs attention' }); });
});
