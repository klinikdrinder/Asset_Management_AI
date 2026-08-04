import{requireProtectedPage}from"../../auth";import{FolderIndex}from"../../library-ui";export default async function Page(){await requireProtectedPage("ADMIN");return <FolderIndex admin/>}
