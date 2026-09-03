import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MarksPanel } from '../pages/faculty/FacultyDashboard';
import { api } from '../services/api';

vi.mock('../services/api', () => ({
  api: { marksPolicy: vi.fn(), marks: vi.fn() },
}));

const policy = { assessments: [
  { internal: 1, label: 'CIE-1', max_marks: 50 },
  { internal: 2, label: 'CIE-2', max_marks: 50 },
  { internal: 3, label: 'CIE-3', max_marks: 50 },
] };
const assignment = { subject: '23AI51' };
const roster = [
  { usn: '4MT23AI001', name: 'Asha' },
  { usn: '4MT23AI002', name: 'Bala' },
];

function renderMarksPanel(overrides = {}) {
  return render(<MarksPanel token="token" assignment={assignment} roster={roster} onSubmitted={vi.fn()} {...overrides} />);
}

async function readyPanel() {
  await screen.findByText('Maximum marks: 50');
}

describe('Faculty marks entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.marksPolicy.mockResolvedValue(policy);
    api.marks.mockResolvedValue({ accepted: 2, rejected: [] });
  });

  it('keeps blank inputs blank and blocks submission with row-level errors', async () => {
    renderMarksPanel();
    await readyPanel();
    expect(screen.getByLabelText('Marks for Asha')).toHaveValue(null);
    fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
    expect(await screen.findAllByText('Mark is required.')).toHaveLength(2);
    expect(screen.getByText('2 students still require marks.')).toBeInTheDocument();
    expect(api.marks).not.toHaveBeenCalled();
  });

  it('treats an explicitly entered zero as valid and sends numeric marks only after confirmation', async () => {
    renderMarksPanel();
    await readyPanel();
    fireEvent.change(screen.getByLabelText('Marks for Asha'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Marks for Bala'), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save marks' }));
    await waitFor(() => expect(api.marks).toHaveBeenCalledWith('token', {
      subject_code: '23AI51', internal: 1,
      entries: [{ usn: '4MT23AI001', marks: 0 }, { usn: '4MT23AI002', marks: 25 }],
    }));
  });

  it('shows negative and excessive mark errors without sending a request', async () => {
    renderMarksPanel();
    await readyPanel();
    fireEvent.change(screen.getByLabelText('Marks for Asha'), { target: { value: '-1' } });
    fireEvent.change(screen.getByLabelText('Marks for Bala'), { target: { value: '51' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
    expect(await screen.findByText('Mark cannot be negative.')).toBeInTheDocument();
    expect(screen.getByText('Mark cannot exceed 50.')).toBeInTheDocument();
    expect(api.marks).not.toHaveBeenCalled();
  });

  it('uses the selected assessment policy as the input maximum', async () => {
    renderMarksPanel();
    await readyPanel();
    const input = screen.getByLabelText('Marks for Asha');
    expect(input).toHaveAttribute('max', '50');
    fireEvent.change(screen.getByLabelText('Assessment'), { target: { value: '2' } });
    expect(screen.getByText('Maximum marks: 50')).toBeInTheDocument();
    expect(input).toHaveAttribute('max', '50');
  });

  it('displays backend validation errors without losing valid drafts', async () => {
    api.marks.mockRejectedValue(new Error('A server validation error occurred.'));
    renderMarksPanel();
    await readyPanel();
    fireEvent.change(screen.getByLabelText('Marks for Asha'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('Marks for Bala'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save marks' }));
    expect(await screen.findByText('A server validation error occurred.')).toBeInTheDocument();
    expect(screen.getByLabelText('Marks for Asha')).toHaveValue(12);
    expect(screen.getByLabelText('Marks for Bala')).toHaveValue(20);
  });
});
