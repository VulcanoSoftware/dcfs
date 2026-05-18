import { createTheme } from '@mui/material/styles';

// Discord "Blurple" color scheme
export const discordTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#5865F2',   // Discord Blurple
      dark: '#4752C4',
      light: '#7983F5',
    },
    secondary: {
      main: '#57F287',   // Discord Green
      dark: '#3ba55c',
      light: '#7bf5a4',
    },
    background: {
      default: '#313338',  // Discord dark background
      paper: '#2B2D31',    // Discord sidebar/card bg
    },
    text: {
      primary: '#DBDEE1',
      secondary: '#949BA4',
    },
    error: { main: '#ED4245' },
    warning: { main: '#FEE75C' },
    success: { main: '#57F287' },
  },
  typography: {
    fontFamily: 'Whitney, "Helvetica Neue", Helvetica, Arial, sans-serif',
    h4: { fontWeight: 700, fontSize: '1.5rem' },
    h5: { fontWeight: 700, fontSize: '1.25rem' },
    h6: { fontWeight: 600, fontSize: '1rem' },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 4,
          fontWeight: 500,
        },
        contained: {
          boxShadow: 'none',
          '&:hover': { boxShadow: 'none', opacity: 0.9 },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 8, backgroundImage: 'none' },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 4,
            backgroundColor: '#1E1F22',
            '& fieldset': { borderColor: '#1E1F22' },
            '&:hover fieldset': { borderColor: '#5865F2' },
            '&.Mui-focused fieldset': { borderColor: '#5865F2' },
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 8, backgroundColor: '#2B2D31' },
      },
    },
  },
});
