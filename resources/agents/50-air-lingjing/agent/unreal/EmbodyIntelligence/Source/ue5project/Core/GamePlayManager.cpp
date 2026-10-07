// Fill out your copyright notice in the Description page of Project Settings.


#include "GamePlayManager.h"

FGamePlayManager* FGamePlayManager::Get()
{
	static FGamePlayManager Instance;
	return &Instance;
}
