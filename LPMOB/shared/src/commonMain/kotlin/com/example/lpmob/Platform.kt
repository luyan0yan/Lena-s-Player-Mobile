package com.example.lpmob

interface Platform {
    val name: String
}

expect fun getPlatform(): Platform