import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import App from '../App.jsx'

describe('App', () => {
  it('renders the home page by default', () => {
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )
    expect(screen.getByText(/PlagioScale/i)).toBeInTheDocument()
  })
})
