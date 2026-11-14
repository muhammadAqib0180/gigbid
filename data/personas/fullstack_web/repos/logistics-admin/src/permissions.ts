export const can = (role: Role, action: Action) => POLICY[role].includes(action);
