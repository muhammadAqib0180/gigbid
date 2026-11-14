export const recipeLoader = new DataLoader((ids) => prisma.recipe.findMany({ where: { id: { in: ids } } }));
