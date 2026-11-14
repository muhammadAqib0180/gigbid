alter table entries enable row level security;
create policy "own rows" on entries for select using (auth.uid() = user_id);
