import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthProvider } from '../context/AuthContext';
import LoginPage from '../pages/auth/LoginPage';
import { ConfirmDialog, ErrorState } from '../components/ui';
import { api } from '../services/api';

vi.mock('../services/api', () => ({ api: { login: vi.fn() }, setUnauthorizedHandler: vi.fn(), ApiError: class ApiError extends Error {} }));
const renderLogin = () => render(<BrowserRouter><AuthProvider><LoginPage /></AuthProvider></BrowserRouter>);

describe('login', () => {
  beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });
  it('validates required credentials', () => { renderLogin(); fireEvent.click(screen.getByRole('button', { name: /sign in to student/i })); expect(screen.getByRole('alert')).toHaveTextContent('Enter your ID and password'); });
  it('uses the authenticated role for redirect state', async () => { api.login.mockResolvedValue({ token: 'token', user: { role: 'faculty', name: 'Faculty' }, ai_mode: 'lexicon' }); renderLogin(); fireEvent.change(screen.getByLabelText(/user id/i), { target: { value: 'aiml.f02' } }); fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'faculty123' } }); fireEvent.click(screen.getByRole('button', { name: /sign in to student/i })); await waitFor(() => expect(api.login).toHaveBeenCalledWith('aiml.f02', 'faculty123')); expect(JSON.parse(localStorage.getItem('mawos_user'))).toMatchObject({ role: 'faculty' }); });
});

describe('shared interaction states', () => {
  it('requires confirmation before calling an admin action', () => { const confirm = vi.fn(); render(<ConfirmDialog open title="Allot seats?" onConfirm={confirm} onClose={() => {}}>This changes data.</ConfirmDialog>); expect(confirm).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: 'Confirm' })); expect(confirm).toHaveBeenCalledTimes(1); });
  it('shows backend error state', () => { render(<ErrorState error={new Error('Backend offline')} />); expect(screen.getByText('Backend offline')).toBeInTheDocument(); });
});
