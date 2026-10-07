// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

/**
 * 
 */
class UE5PROJECT_API FGamePlayManager 
{
public:
	static FGamePlayManager* Get();
	
	TWeakObjectPtr<UWorld> WorldContext;

};
