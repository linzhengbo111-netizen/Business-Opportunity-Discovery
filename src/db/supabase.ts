import { createClient } from "@supabase/supabase-js";

const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)
  || "https://zbxogsfnhagcavbvhypk.supabase.co";
const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined)
  || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
