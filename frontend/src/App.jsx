import { useEffect, useState } from 'react'
import { ArrowRight, Check, Eye, EyeOff, KeyRound, LockKeyhole, Pencil, Plus, ShieldCheck, Trash2, UserRound, X } from 'lucide-react'
import './management.css'

const accounts = {
  admin: { label: 'Administrator', email: import.meta.env.VITE_ADMIN_EMAIL || 'ashish@authmantra.com', password: import.meta.env.VITE_ADMIN_PASSWORD || 'AdminPass123!', name: 'Ashish' },
  user: { label: 'POC user', email: import.meta.env.VITE_TEST_USER_EMAIL || 'poc@authmantra.com', password: import.meta.env.VITE_TEST_USER_PASSWORD || 'TestPass123!', name: 'POC User' },
}
const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function UserManagement({ session }) {
  const [users, setUsers] = useState([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState({ display_name: '', email: '', password: '', role: 'user' })

  async function request(path, options = {}) {
    const response = await fetch(`${apiUrl}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || 'The request could not be completed.')
    }
    return response.status === 204 ? null : response.json()
  }

  async function loadUsers() {
    setBusy(true)
    setError('')
    try {
      setUsers(await request('/api/users'))
    } catch (exception) {
      setError(exception.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { loadUsers() }, [])

  function startCreate() {
    setEditingId(null)
    setFormOpen(true)
    setForm({ display_name: '', email: '', password: '', role: 'user' })
    setMessage('')
    setError('')
  }

  function startEdit(user) {
    setEditingId(user.id)
    setFormOpen(true)
    setForm({ display_name: user.display_name, email: user.email, password: '', role: user.role })
    setMessage('')
    setError('')
  }

  async function saveUser(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    const payload = { display_name: form.display_name, email: form.email, role: form.role }
    if (form.password) payload.password = form.password
    try {
      await request(editingId ? `/api/users/${editingId}` : '/api/users', {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      setMessage(editingId ? 'User updated.' : 'User added.')
      setEditingId(null)
      setFormOpen(false)
      setForm({ display_name: '', email: '', password: '', role: 'user' })
      await loadUsers()
    } catch (exception) {
      setError(exception.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeUser(user) {
    if (!window.confirm(`Delete ${user.display_name} (${user.email})?`)) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await request(`/api/users/${user.id}`, { method: 'DELETE' })
      setMessage('User deleted.')
      await loadUsers()
    } catch (exception) {
      setError(exception.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="user-admin" aria-label="User management">
      <div className="admin-heading"><div><p className="eyebrow">ADMINISTRATION</p><h2>User directory</h2></div><button className="add-user-button" type="button" onClick={startCreate}><Plus size={16} /> Add user</button></div>
      <p className="admin-subtitle">Manage workspace access and account roles.</p>
      {(message || error) && <p className={error ? 'admin-alert error' : 'admin-alert'} role="status">{error || message}</p>}
      <div className="users-table-wrap">
        <table className="users-table"><thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{users.map((user) => <tr key={user.id}><td><span className="table-avatar">{user.display_name.split(' ').map((part) => part[0]).join('').slice(0, 2)}</span>{user.display_name}</td><td>{user.email}</td><td><span className={`role-tag ${user.role}`}>{user.role}</span></td><td className="row-actions"><button type="button" aria-label={`Edit ${user.email}`} title="Edit user" onClick={() => startEdit(user)}><Pencil size={15} /></button><button type="button" aria-label={`Delete ${user.email}`} title="Delete user" onClick={() => removeUser(user)} disabled={user.id === session.user.id}><Trash2 size={15} /></button></td></tr>)}
          {users.length === 0 && <tr><td colSpan="4" className="empty-users">{busy ? 'Loading users…' : 'No users found.'}</td></tr>}</tbody></table>
      </div>
      {formOpen && <form className="user-form" onSubmit={saveUser}>
        <div className="user-form-heading"><h3>{editingId ? 'Update user' : 'Add user'}</h3><button type="button" className="close-form" aria-label="Close form" onClick={() => setFormOpen(false)}><X size={17} /></button></div>
        <div className="user-form-grid"><label>Name<input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} required maxLength="100" /></label><label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label>Password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength="8" required={!editingId} placeholder={editingId ? 'Leave blank to keep current' : 'At least 8 characters'} /></label><label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="user">User</option><option value="admin">Admin</option></select></label></div>
        <button className="save-user-button" type="submit" disabled={busy}>{busy ? 'Saving…' : editingId ? 'Save changes' : 'Create user'} <ArrowRight size={15} /></button>
      </form>}
      {!formOpen && <button className="refresh-users" type="button" onClick={loadUsers} disabled={busy}>Refresh directory</button>}
    </section>
  )
}

export default function App() {
  const [mode, setMode] = useState('admin')
  const [email, setEmail] = useState(accounts.admin.email)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState(null)

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1))
    const oktaToken = fragment.get('access_token')
    const oktaError = fragment.get('auth_error')
    if (oktaError) {
      window.history.replaceState(null, '', window.location.pathname)
      const errorMessages = {
        okta_not_configured: 'Okta sign-in is not configured on the backend yet.',
        okta_provider_error: 'Okta did not authorize this sign-in. Check the Okta app settings and try again.',
        okta_state_invalid: 'The Okta sign-in session expired or could not be verified. Try signing in again.',
        okta_nonce_invalid: 'Okta identity verification failed. Try signing in again.',
        okta_subject_mismatch: 'The Okta ID token and UserInfo response identify different users. Contact your administrator.',
        okta_email_unverified: 'Verify your email address in Okta, then try signing in again.',
        okta_user_not_linked: 'Your Okta email does not match an existing AuthMantra user account.',
        okta_exchange_failed: 'The backend could not exchange the Okta authorization code. Check the Okta client settings and callback URI.',
        okta_token_invalid: 'The backend could not validate the Okta identity token. Check the issuer and authorization server configuration.',
      }
      setError(errorMessages[oktaError] || 'Okta sign-in could not be completed. Check your account and try again.')
      return
    }
    if (oktaToken) {
      window.history.replaceState(null, '', window.location.pathname)
      setLoading(true)
      fetch(`${apiUrl}/api/auth/me`, { headers: { Authorization: `Bearer ${oktaToken}` } })
        .then(async (response) => {
          const user = await response.json()
          if (!response.ok) throw new Error(user.detail || 'Okta sign-in could not be completed.')
          setSession({ access_token: oktaToken, user })
        })
        .catch((exception) => setError(exception.message || 'Okta sign-in could not be completed.'))
        .finally(() => setLoading(false))
    }
  }, [])

  function chooseAccount(nextMode) {
    setMode(nextMode)
    setEmail(accounts[nextMode].email)
    setPassword('')
    setError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${apiUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Unable to sign in. Please try again.')
      setSession(result)
    } catch (exception) {
      setError(exception.message || 'The API could not be reached. Check that the containers are running.')
    } finally {
      setLoading(false)
    }
  }

  if (session) {
    return (
      <main className="app-shell">
        <header className="topbar"><a className="wordmark" href="/"><span className="brand-mark"><ShieldCheck size={19} /></span>authmantra</a><span className="environment"><span />Local environment</span></header>
        <section className="success-panel">
          <div className="success-icon"><Check size={28} /></div>
          <p className="eyebrow">ACCESS GRANTED</p>
          <h1>Welcome back,<br /><em>{session.user.display_name.split(' ')[0]}.</em></h1>
          <p className="success-copy">You’re signed in to AuthMantra as <strong>{session.user.role}</strong>.</p>
          <div className="identity-row"><span className="avatar">{session.user.display_name.split(' ').map((part) => part[0]).join('')}</span><span><strong>{session.user.display_name}</strong><small>{session.user.email}</small></span><span className="role-tag">{session.user.role}</span></div>
          {session.user.role === 'admin' ? <UserManagement session={session} /> : <div className="readonly-note"><LockKeyhole size={16} /><span><strong>Read-only access</strong><small>Your account can view this workspace but cannot change user accounts.</small></span></div>}
          <button className="quiet-button" onClick={() => { setSession(null); setPassword('') }}>Sign out <ArrowRight size={16} /></button>
        </section>
        <footer className="footer"><span>AUTHMANTRA <b>·</b> ACCESS PORTAL</span><span>SECURE BY DESIGN</span></footer>
      </main>
    )
  }

  return (
    <main className="app-shell">
      <header className="topbar"><a className="wordmark" href="/"><span className="brand-mark"><ShieldCheck size={19} /></span>authmantra</a><span className="environment"><span />Local environment</span></header>
      <div className="layout">
        <section className="intro" aria-label="Welcome">
          <div className="intro-rule"><span>IDENTITY, IN GOOD HANDS</span><span>01 — 03</span></div>
          <div className="intro-copy">
            <p className="eyebrow">YOUR WORKSPACE, SECURED</p>
            <h1>Good to<br />have you <em>back.</em></h1>
            <p className="intro-desc">A considered space for the people<br className="desktop-break" /> who keep things moving.</p>
          </div>
          <div className="orbit-art" aria-hidden="true">
            <div className="orbit orbit-one"><span className="orbit-dot dot-one" /></div>
            <div className="orbit orbit-two"><span className="orbit-dot dot-two" /></div>
            <div className="orbit-core"><ShieldCheck size={31} strokeWidth={1.5} /></div>
            <span className="orbit-caption">TRUST, BY DESIGN</span>
          </div>
          <div className="intro-bottom"><span>01 / AUTHENTICATE</span><span>BUILT FOR CLARITY <span className="spark">✳</span></span></div>
        </section>

        <section className="form-side" aria-label="Sign in form">
          <div className="form-wrap">
            <div className="form-heading"><p className="eyebrow">SIGN IN TO CONTINUE</p><h2>Welcome in.</h2><p>Use your account details to access your workspace.</p></div>
            <div className="account-switch" role="tablist" aria-label="Choose a demo account">
              <button className={mode === 'admin' ? 'selected' : ''} onClick={() => chooseAccount('admin')} role="tab" aria-selected={mode === 'admin'}><ShieldCheck size={16} /> Admin</button>
              <button className={mode === 'user' ? 'selected' : ''} onClick={() => chooseAccount('user')} role="tab" aria-selected={mode === 'user'}><UserRound size={16} /> POC user</button>
            </div>
            <>
              <button className="okta-button" type="button" onClick={() => window.location.assign(`${apiUrl}/api/auth/okta/login`)}><ShieldCheck size={17} /> Continue with Okta <ArrowRight size={16} /></button>
              <div className="auth-divider"><span>OR USE EMAIL</span></div>
            </>
            <form onSubmit={handleSubmit}>
              <label htmlFor="email">Email address</label>
              <div className="input-wrap"><span className="field-icon"><UserRound size={17} /></span><input id="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
              <div className="label-row"><label htmlFor="password">Password</label><span className="secure-label"><LockKeyhole size={12} /> ENCRYPTED</span></div>
              <div className="input-wrap"><span className="field-icon"><KeyRound size={17} /></span><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} required /><button className="visibility-button" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>
              {error && <p className="error-message" role="alert"><X size={15} />{error}</p>}
              <button className="submit-button" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}<ArrowRight size={17} /></button>
            </form>
            <div className="demo-note"><span className="note-icon"><LockKeyhole size={15} /></span><span><strong>{accounts[mode].label} demo</strong><small>Password: {accounts[mode].password}</small></span><button type="button" className="use-demo" onClick={() => setPassword(accounts[mode].password)}>Use <ArrowRight size={14} /></button></div>
            <p className="terms">By continuing, you agree to keep this workspace secure.</p>
          </div>
          <div className="form-bottom"><span>NEED HELP? <a href="mailto:support@example.com">CONTACT SUPPORT</a></span><span>v1.0.0</span></div>
        </section>
      </div>
      <footer className="footer"><span>AUTHMANTRA <b>·</b> ACCESS PORTAL</span><span>SECURE BY DESIGN</span></footer>
    </main>
  )
}
