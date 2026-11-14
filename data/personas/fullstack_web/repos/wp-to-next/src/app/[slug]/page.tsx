export const revalidate = 300;
export default async function Page({ params }) { return <Article post={await getPost(params.slug)} />; }
