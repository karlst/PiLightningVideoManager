"use strict";


export async function postJson(url)
{
    const response =
        await fetch(
            url,
            {
                method: "POST"
            }
        );

    return await response.json();
}


export async function getJson(url)
{
    const response =
        await fetch(
            url
        );

    return await response.json();
}
